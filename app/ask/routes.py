import logging
import time

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.answer.llm import complete_json
from app.ask.service import Deps, answer_question
from app.catalog.registry import load_models
from app.core.config import get_settings
from app.core.db import get_conn
from app.core.errors import AppError, make_error
from app.core.observability import get_tracer
from app.retrieval.embeddings import embed_query
from app.retrieval.search import fetch_manual_pages, search_hybrid, search_vector

log = logging.getLogger(__name__)
router = APIRouter()


class AskBody(BaseModel):
    # 빠진 값도 서버 검사(INVALID_MODEL·EMPTY_QUESTION)로 보내려고 선택 항목으로 둔다(422 대신 400)
    model_id: str | None = None
    question: str | None = None


def get_deps() -> Deps:
    models = {m["id"]: m for m in load_models()}
    timings: dict[str, int] = {}

    def search(model_id: str, query_vec: list[float], question: str, k: int):
        start = time.perf_counter()
        with get_tracer().span("db_connect"):
            conn = get_conn()  # 접속은 여기서 일어난다(with는 끝날 때 닫기만 함)
        timings["db_connect_ms"] = int((time.perf_counter() - start) * 1000)
        with conn:
            if get_settings().search_mode == "hybrid":  # v2b: 질문 단어 + 코드 키워드를 섞음
                return search_hybrid(conn, model_id, query_vec, question, k)
            return search_vector(conn, model_id, query_vec, k)

    def diagnostic(model_id: str):
        pages = [int(ref.split(":")[1]) for ref in models[model_id].get("diagnostic_refs", [])]
        if not pages:
            return []
        with get_conn() as conn:
            return fetch_manual_pages(conn, model_id, pages)

    return Deps(embed_query=embed_query, search=search, complete=lambda msgs: complete_json(msgs, get_settings(), usage=timings),
                supported_ids=set(models), official_url=lambda m: models[m]["official_url"], brand=lambda m: models[m]["brand"], timings=timings,
                diagnostic=diagnostic)


def _error(e: AppError) -> JSONResponse:
    return JSONResponse(status_code=e.status, content={"error_code": e.code, "message": e.message})


@router.post("/api/ask")
def ask(body: AskBody, debug: bool = False, deps: Deps = Depends(get_deps)):
    try:
        return answer_question(body.model_id, body.question, deps, get_settings(), debug=debug)
    except AppError as e:
        return _error(e)
    except Exception as e:
        log.error("ask 실패: %s", type(e).__name__)  # 메시지에 접속 주소·키가 섞일 수 있어 종류만 남긴다
        return JSONResponse(status_code=500, content={"error_code": "SERVICE_UNAVAILABLE",
                                                      "message": make_error("SERVICE_UNAVAILABLE").message})


def register_error_handlers(app: FastAPI) -> None:
    """본문을 읽지 못하거나 형식이 틀린 요청도 화면이 error_code로 안내할 수 있게 같은 형식으로 돌려준다."""

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return _error(make_error("INVALID_REQUEST"))

    @app.exception_handler(StarletteHTTPException)
    async def unreadable_body(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 400:  # "There was an error parsing the body" 등
            return _error(make_error("INVALID_REQUEST"))
        return await http_exception_handler(request, exc)  # 404·405 등은 기본 처리
