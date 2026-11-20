"""조각 설명 붙이기(v1.95): 조각마다 AI가 쓴 짧은 설명을 본문 앞에 붙여 임베딩한다(검색용으로만).

저장 본문·화면 인용·답변 AI·인용 검사는 원문 그대로다. 설정(CHUNK_CONTEXT_MODEL)이 비면 아무것도 하지 않는다.
한 번 쓴 설명은 git 밖 파일(DESC_PATH)에 남기고, 측정·운영 반영·이후 적재가 모두 그 설명을 다시 쓴다.
"""
import datetime
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ingest.load import ROOT, chunks_with_sources

PROMPT_PATH = ROOT / "ingest" / "prompts" / "chunk_context_v1.txt"
DESC_PATH = ROOT / "data" / "chunk_context" / "descriptions.jsonl"
MAX_DESC_LEN = 150
MAX_OUTPUT_TOKENS = 1000  # 추론 토큰 포함, 쓴 만큼만 과금
TIMEOUT_SECONDS = 60
SCOPE = {"manual": "설명서 한 쪽의 글 전체", "guide": "해결 가이드 글 전체"}
CONTEXT_FORMAT = {
    "type": "json_schema",
    "name": "chunk_context",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"description": {"type": "string"}},
        "required": ["description"],
        "additionalProperties": False,
    },
}


@dataclass(frozen=True)
class ContextSpec:
    model: str
    effort: str


CANDIDATE_CONTEXT = ContextSpec("gpt-6-luna", "low")


@dataclass(frozen=True)
class ContextItem:
    doc_id: str
    doc_type: str
    page: int | None
    content: str
    source: str
    doc_label: str
    chunk_id: int | None = None  # 기록에만 남긴다. 다시 적재하면 번호가 바뀌어 찾는 키에는 넣지 않는다(결정기록 037)


class MissingDescriptions(SystemExit):
    def __init__(self, count: int):
        super().__init__(f"설명이 없는 조각 {count}개: 멈춤(다시 돌릴지는 사용자가 정함)")
        self.count = count


def doc_label(doc: dict, models: dict[str, dict]) -> str:
    return doc["title"] + " — " + " · ".join(models[m]["display_name"] for m in doc["model_ids"])


def _items(doc: dict, chunks_src: list[tuple[int | None, str, str]], models: dict[str, dict]) -> list[ContextItem]:
    label = doc_label(doc, models)
    return [ContextItem(doc["id"], doc["doc_type"], page, text, source, label) for page, text, source in chunks_src]


def context_items(doc: dict, models: dict[str, dict]) -> list[ContextItem]:
    return _items(doc, chunks_with_sources(doc)[0], models)


def prompt_sha256() -> str:
    return hashlib.sha256(PROMPT_PATH.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def build_prompt(item: ContextItem) -> str:
    values = {"doc_label": item.doc_label, "scope": SCOPE[item.doc_type], "source": item.source, "chunk": item.content}
    template = PROMPT_PATH.read_text(encoding="utf-8")
    # 한 번에 채운다: 앞에서 넣은 글에 "{chunk}" 같은 글자가 있어도 다시 바뀌지 않는다
    return re.sub(r"\{(doc_label|scope|source|chunk)\}", lambda m: values[m.group(1)], template)


def clean_description(output_text: str) -> str | None:
    try:
        text = json.loads(output_text)["description"]
    except (ValueError, TypeError, KeyError):
        return None
    if not isinstance(text, str):
        return None
    text = " ".join(text.split())
    return text if 0 < len(text) <= MAX_DESC_LEN else None


def describe_chunk(item: ContextItem, spec: ContextSpec, client) -> tuple[str | None, dict]:
    """요청 1회. API 오류면 (None, 오류 종류). 형식이 어긋나면 (None, "format")."""
    try:
        resp = client.responses.create(
            model=spec.model,
            input=[{"role": "user", "content": build_prompt(item)}],
            max_output_tokens=MAX_OUTPUT_TOKENS,
            reasoning={"effort": spec.effort},
            text={"format": CONTEXT_FORMAT},
        )
    except Exception as e:
        return None, {"input_tokens": 0, "output_tokens": 0, "error": type(e).__name__}  # 메시지에 키가 섞일 수 있어 종류만
    u = getattr(resp, "usage", None)
    usage = {"input_tokens": getattr(u, "input_tokens", 0), "output_tokens": getattr(u, "output_tokens", 0)}
    desc = clean_description(resp.output_text)
    return desc, usage | {"error": None if desc else "format"}


def _content_sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def record_key(item: ContextItem, spec: ContextSpec, prompt_sha: str) -> tuple:
    return (item.doc_id, item.page, _content_sha(item.content), spec.model, spec.effort, prompt_sha)


def stored_key(r: dict) -> tuple:
    """설명 파일 한 줄의 찾는 키(record_key와 같은 순서)."""
    return (r["doc_id"], r["page"], r["content_sha256"], r["model"], r["effort"], r["prompt_sha256"])


def _stored(path: Path) -> dict[tuple, str]:
    """키 → 설명. 두 번 다 실패한 조각의 줄(description null)은 "설명 있음"으로 세지 않는다(줄 순서와 상관없이 성공 줄)."""
    if not path.exists():
        return {}
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["description"]:
            found.setdefault(stored_key(r), r["description"])
    return found


def _client():
    import openai

    from app.core.config import get_settings
    return openai.OpenAI(api_key=get_settings().openai_api_key, timeout=TIMEOUT_SECONDS, max_retries=0)


def describe_all(items: list[ContextItem], spec: ContextSpec, *, path: Path = DESC_PATH, client=None,
                 call=describe_chunk, allow_new: bool = True) -> list[str]:
    """파일에 같은 키의 설명이 있으면 그대로 쓰고(부르지 않음), 없으면 최대 2회 불러 결과를 파일에 한 줄 덧붙인다
    (두 번 다 실패하면 description null). 끝까지 빠진 조각이 있으면 모두 돈 뒤 MissingDescriptions.
    allow_new=False면 부르지 않고 바로 낸다."""
    psha = prompt_sha256()
    stored = _stored(path)
    keys = [record_key(item, spec, psha) for item in items]
    missing = [k for k in keys if k not in stored]
    if missing and not allow_new:
        raise MissingDescriptions(len(missing))
    if missing and client is None and call is describe_chunk:
        client = _client()
    out, failed = [], 0
    for item, key in zip(items, keys):
        if key in stored:
            out.append(stored[key])
            continue
        desc, tokens = None, {"input_tokens": 0, "output_tokens": 0}
        for attempt in (1, 2):  # 한 번만 쓴다. 다시 부르는 것은 API 오류·형식 오류가 난 그 조각만 1회
            desc, usage = call(item, spec, client)
            tokens = {k: tokens[k] + usage.get(k, 0) for k in tokens}
            if desc:
                break
        # 두 번 다 실패해도 키·시도 횟수·토큰을 description null로 남긴다(다시 돌린 수와 실제 비용을 세기 위해, 검토 M1)
        record = {"doc_id": item.doc_id, "page": item.page, "content_sha256": key[2], "model": spec.model,
                  "effort": spec.effort, "prompt_sha256": psha, "chunk_id": item.chunk_id, "description": desc or None,
                  "attempts": attempt, **tokens, "created": datetime.datetime.now().isoformat(timespec="seconds")}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        if not desc:
            failed += 1
            out.append("")
            continue
        stored[key] = desc
        out.append(desc)
    if failed:
        raise MissingDescriptions(failed)
    return out


def embedding_input(description: str, content: str) -> str:
    return f"{description}\n{content}"


def ingest_texts(doc: dict, chunks_src: list[tuple[int | None, str, str]], settings, models: dict[str, dict], *,
                 describe=describe_all) -> list[str]:
    """적재 때 임베딩할 글. 설정이 비면 본문 그대로(지금 운영과 글자까지 같음), 켜지면 설명 + 줄바꿈 + 본문."""
    if not settings.chunk_context_model:
        return [text for _, text, _ in chunks_src]
    items = _items(doc, chunks_src, models)
    descs = describe(items, ContextSpec(settings.chunk_context_model, settings.chunk_context_reasoning_effort))
    return [embedding_input(d, item.content) for d, item in zip(descs, items, strict=True)]
