"""검색 개선 실험 색인 만들기(계획 2026-11-09-search-paraphrase-plan). 운영 표(chunks)는 읽기만 하고 chunk_variants에만 넣는다.

M1(Task 4): 조각 앞에 "모델 · 문서 제목 · 장 이름 · 쪽 소제목" 한 줄을 붙여 다시 임베딩한다.
- 장 이름: 쪽 첫 두 줄 중 쪽 번호가 붙은 머리글("사용하기 15", "16 사용하기"). 삼성은 머리글이 "18 한국어"라 그 위 줄이 장 이름
- 소제목: 머리글 다음 6줄 안의 첫 제목형 줄(2~30자, 글머리표·번호·주의 표시로 시작하지 않고, 문장처럼 끝나지 않음)
- 쪽의 첫 조각에서 뽑아 그 쪽의 모든 조각에 쓴다. 없으면 앞쪽 값을 이어받는다(장이 바뀌면 소제목은 이어받지 않음). 가이드는 모델·문서 제목만

사용법: python -m measure.search_variants m1            (미리보기: 쪽별 제목을 measure/out/에 쓰고 끝)
        python -m measure.search_variants m1 --apply    (임베딩해서 chunk_variants에 넣음. 이미 행이 있으면 멈춤 — 지우기는 사용자 확인)
        python -m measure.search_variants m2 --sample   (M2 시험 생성: 문서 5개에서 조각 1개씩, 결과는 measure/out/m2-sample.json, DB에 넣지 않음)
        python -m measure.search_variants m3 --draft    (M3 용어 사전 초안: 설명서마다 기능 이름 뽑기 → 평소 표현, 결과는 measure/out/m3-terms-draft.json)
        python -m measure.search_variants m3 --reduce   (규칙 ① 이름 종류 분류로 줄이기 + ③ 겹친 표현 지우기, 검토표 measure/out/m3-terms-reduced.md)
        python -m measure.search_variants m3 --tidy     (띄어쓰기·끝 "기능"만 다른 이름 합치기 → 규칙 ③ 다시, 검토표 다시 만들기, AI 없음)
        python -m measure.search_variants m3 --finalize (사용자 검토 m3_review.json 반영 → 이름 끝 합치기 → 규칙 ③ → 확정 사전 measure/m3_terms.json, AI 없음)
"""
import argparse
import csv
import json
import random
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
M2_PROMPT = (Path(__file__).resolve().parent / "prompts" / "m2_questions_v3.txt").read_text(encoding="utf-8")  # v1·v2는 기록용
_QA_LIST = {"type": "array", "items": {"type": "object", "required": ["question", "evidence"], "additionalProperties": False,
                                       "properties": {"question": {"type": "string"}, "evidence": {"type": "string"}}}}
M2_FORMAT = {"type": "json_schema", "name": "questions", "strict": True,
             "schema": {"type": "object", "required": ["plain", "named"], "additionalProperties": False,
                        "properties": {"plain": _QA_LIST, "named": _QA_LIST}}}
M2_LIMITS = {"plain": 3, "named": 2}  # 기능 이름 없이 3개 + 기능 이름을 쓰는 2개
_ASKS_NUMBER = re.compile(r"몇|며칠")
_GENERIC_WORDS = {"사용", "설정", "방법", "관리", "기능", "확인", "청소", "안내", "살펴보", "살펴보기", "및", "하기"}
_NAME_ENDINGS = ("설정하기", "기능", "운전", "하기", "코스", "버튼", "옵션")  # M3 이름 합치기: 떼고 같으면 같은 이름
_SKIP_START = re.compile(r"^([•\-–※*·→]|\d|[a-z]\s|[①-⑳]|\(|주의|경고|참고|알아두기)")
_SENTENCE_END = re.compile(r"([.:?!]|요|다|[을를이가은는에의로와과고며서면])$")


def page_heading(page: int, text: str) -> tuple[str | None, str | None]:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    section, start = None, 0
    for i, line in enumerate(lines[:2]):
        m = re.fullmatch(rf"{page}\s+(.+)|(.+?)\s+{page}", line)
        if m:
            name = (m[1] or m[2]).strip()
            section = (lines[0] if i == 1 else None) if name == "한국어" else name
            start = i + 1
            break
    sub = next((line for line in lines[start:start + 6] if 2 <= len(line) <= 30 and line != section
                and not _SKIP_START.match(line) and ". " not in line and not _SENTENCE_END.search(line)), None)
    return section, sub


def doc_headings(pages: list[tuple[int, str]]) -> dict[int, tuple[str | None, str | None]]:
    """(쪽, 그 쪽 첫 조각) → 쪽별 (장 이름, 소제목). 없는 값은 앞쪽에서 이어받는다"""
    out, prev = {}, (None, None)
    for page, text in sorted(pages):
        section, sub = page_heading(page, text)
        same_section = section in (None, prev[0])
        section = section or prev[0]
        sub = sub or (prev[1] if same_section else None)
        out[page] = prev = (section, sub)
    return out


def m1_text(model_names: list[str], doc_title: str, heading: tuple[str | None, str | None], content: str) -> str:
    return " · ".join([", ".join(model_names), doc_title, *[h for h in heading if h]]) + "\n" + content


def build_m1(conn, display_names: dict[str, str]) -> list[dict]:
    rows = conn.execute("""SELECT c.id, c.doc_id, d.title, c.page, c.content,
                                  (SELECT array_agg(model_id ORDER BY model_id) FROM document_models WHERE doc_id = c.doc_id)
                           FROM chunks c JOIN documents d ON d.id = c.doc_id ORDER BY c.doc_id, c.page, c.id""").fetchall()
    first_of_page = {}
    for cid, doc_id, _, page, content, _ in rows:
        if page is not None:
            first_of_page.setdefault((doc_id, page), content)
    headings = {}
    for doc_id in {d for d, _ in first_of_page}:
        for page, h in doc_headings([(p, t) for (d, p), t in first_of_page.items() if d == doc_id]).items():
            headings[(doc_id, page)] = h
    out = []
    for cid, doc_id, title, page, content, models in rows:
        heading = headings.get((doc_id, page), (None, None))
        text = m1_text([display_names[m] for m in models], title, heading, content)
        out.append({"chunk_id": cid, "doc_id": doc_id, "page": page, "title": text.split("\n", 1)[0], "text": text,
                    "sub": heading[1]})
    return out


def build_m2_messages(model_names: list[str], doc_title: str, page: int | None, content: str) -> list[dict]:
    body = content.replace("<", "〈").replace(">", "〉")  # 조각 안 꺾쇠로 구분 표시를 흉내 내지 못하게
    where = f"{page}쪽" if page is not None else "에러 가이드"
    return [{"role": "system", "content": M2_PROMPT},
            {"role": "user", "content": f"모델: {', '.join(model_names)}\n문서: {doc_title} ({where})\n<조각>\n{body}\n</조각>"}]


def check_items(items: list[dict], chunk: str, max_n: int = 5, max_len: int = 60) -> tuple[list[dict], list[dict]]:
    """근거 문장이 조각에 그대로 있는 질문만 남긴다(공백·줄바꿈 차이는 무시). 버린 질문은 이유와 함께 돌려준다"""
    flat = lambda t: " ".join(t.split())
    body, kept, dropped = flat(chunk), [], []
    for it in items:
        q, e = it["question"].strip(), flat(it["evidence"])
        reason = ("근거 없음" if not e else "근거가 조각에 없음" if e not in body
                  else "숫자를 묻는데 근거에 숫자 없음" if _ASKS_NUMBER.search(q) and not re.search(r"\d", e)
                  else "60자 초과" if not q or len(q) > max_len
                  else "중복" if q in {k["question"] for k in kept}
                  else f"{max_n}개 초과" if len(kept) >= max_n else None)
        (dropped if reason else kept).append({"question": q, "evidence": e} | ({"reason": reason} if reason else {}))
    return kept, dropped


_POINTING = re.compile(r"(?:^|\s)(이건|그건|저건|이거|그거|저거|이것|그것|저것|이게|그게|저게)(?=\s|$|[?!.,])")


def subheading_phrases(subheading: str | None) -> list[str]:
    """M1 소제목에서 동작·일반어(청소·설정·및 등)로 끊은 두 단어 이상 묶음(구절). 한 단어(리모컨)는 검사하지 않는다"""
    runs, cur = [], []
    for w in [re.sub(r"하기$", "", w) for w in re.findall(r"[가-힣A-Za-z0-9+]+", subheading or "")]:
        if len(w) < 2 or w in _GENERIC_WORDS:
            runs, cur = runs + [cur], []
        else:
            cur.append(w)
    return [" ".join(r) for r in runs + [cur] if len(r) >= 2]


def check_split(raw: dict, chunk: str, subheading: str | None) -> tuple[dict, list[dict]]:
    """v3: 칸마다 근거 확인(v2 규칙). 가리키는 말(이건·그거 등) 질문, '기능 이름 없이' 칸에 소제목 구절이 든 질문은 버린다"""
    phrases, kept, dropped = subheading_phrases(subheading), {}, []
    for kind, limit in M2_LIMITS.items():
        items = []
        for it in raw[kind]:
            q = it["question"].strip()
            point = _POINTING.search(q)
            hit = next((p for p in phrases if p.replace(" ", "") in q.replace(" ", "")), None) if kind == "plain" else None
            reason = f"가리키는 말({point[1]})" if point else f"기능 이름 없이 칸에 소제목 구절({hit})" if hit else None
            if reason:
                dropped.append({"kind": kind, "question": q, "evidence": " ".join(it["evidence"].split()), "reason": reason})
            else:
                items.append(it)
        kept[kind], bad = check_items(items, chunk, max_n=limit)
        dropped += [{"kind": kind} | d for d in bad]
    return kept, dropped


def merge_variants(terms: dict[str, list[str]], kinds: dict[str, str]) -> tuple[dict, dict, dict]:
    """띄어쓰기만 다르거나 끝에 '기능·운전·하기·설정하기·코스·버튼·옵션'만 붙은 이름을 처음 나온 이름 하나로 합친다(표현은 합집합)"""
    def key(n: str) -> str:
        k = n.replace(" ", "")
        while True:
            end = next((e for e in _NAME_ENDINGS if k.endswith(e) and len(k) > len(e) + 1), None)
            if not end:
                return k
            k = k[:-len(end)]
    first, merged, record = {}, {}, {}
    for n, exprs in terms.items():
        head = first.setdefault(key(n), n)
        if head != n:
            record.setdefault(head, []).append(n)
        merged.setdefault(head, [])
        merged[head] += [e for e in exprs if e not in merged[head]]
    return merged, {n: kinds[n] for n in merged}, record


def apply_review(terms: dict[str, list[str]], review: dict) -> dict[str, list[str]]:
    """사용자 검토 반영: 이름 지우기, 표현 지우기, 표현 바꾸기. 없는 이름·표현이면 멈춘다(오타로 조용히 넘어가지 않게)"""
    out = {n: list(e) for n, e in terms.items()}
    for n in review.get("delete", []):
        del out[n]
    for n, exprs in review.get("remove_expressions", {}).items():
        for e in exprs:
            out[n].remove(e)
    for n, pairs in review.get("replace_expressions", {}).items():
        for old, new in pairs.items():
            out[n][out[n].index(old)] = new
    return out


# ── M3 규칙 ②(측정 전 보완: 어간 비교)와 질문 넓히기 ──
_PARTICLE_ENDS = ("에서", "으로", "하기", "하고", "하게", "하면", "하는", "해서", "은", "을", "를", "이", "가", "에", "로", "와", "과",
                  "도", "만", "의", "요")
_VERB_ENDS = ("기", "고", "게", "면", "는", "서", "지")  # 떼면 '말리'처럼 동사 어간이 남는 말끝(줄임꼴 '말려'도 함께 본다)
_CONTRACT = {20: 6, 13: 14, 8: 9, 18: 4}  # ㅣ→ㅕ(말리→말려), ㅜ→ㅝ(추→춰), ㅗ→ㅘ(나오→나와), ㅡ→ㅓ(끄→꺼)


def _contracted(stem: str) -> str | None:
    code = ord(stem[-1]) - 0xAC00
    if not 0 <= code < 11172 or code % 28:  # 한글이 아니거나 받침이 있으면 줄임꼴 없음
        return None
    v = (code % 588) // 28
    return stem[:-1] + chr(0xAC00 + code - v * 28 + _CONTRACT[v] * 28) if v in _CONTRACT else None


def word_stems(word: str) -> list[str]:
    """말끝 하나를 떼고 남은 앞부분. 동사 말끝을 뗐으면 줄임꼴도(말리기 → 말리, 말려)"""
    for end in sorted(_PARTICLE_ENDS + _VERB_ENDS, key=len, reverse=True):
        if word.endswith(end) and len(word) > len(end):
            stem = word[:-len(end)]
            alt = _contracted(stem) if end in _VERB_ENDS else None
            return [stem] + ([alt] if alt else [])
    return [word]


def _found(stem: str, question: str) -> bool:
    if len(stem) >= 2:
        return stem in question
    return re.search(rf"(?:^|[\s,.?!~]){re.escape(stem)}", question) is not None  # 한 글자 어간은 단어 앞에서만


def expression_matches(expression: str, question: str) -> bool:
    """규칙 ②: 표현의 핵심 단어(두 글자 이상)마다 어간 중 하나가 질문에 있으면 맞춘 것"""
    core = [w for w in expression.split() if len(w) >= 2]
    return bool(core) and all(any(_found(s, question) for s in word_stems(w)) for w in core)


def expand_query(question: str, terms: dict[str, list[str]]) -> str:
    """맞은 표현의 설명서 용어를 질문 뒤에 덧붙인다(사용자 말은 그대로, 이미 있는 용어는 덧붙이지 않음)"""
    flat = question.replace(" ", "")
    add = [n for n, exprs in terms.items()
           if n.replace(" ", "") not in flat and any(expression_matches(e, question) for e in exprs)]
    return " ".join([question] + add)


def sample_chunks(rows: list[dict], doc_ids: list[str], seed: int) -> list[dict]:
    """문서마다 조각 1개(시드 고정). 질문 품질을 훑어보는 시험 생성용"""
    rng = random.Random(seed)
    return [rng.choice([r for r in rows if r["doc_id"] == d]) for d in doc_ids]


# ── M3 용어 사전(Task 6): 설명서에서 기능 이름을 뽑고, 이름마다 평소 표현을 만든다(사용자 검토 전 초안) ──
M3_PROMPTS = {k: (Path(__file__).resolve().parent / "prompts" / f"m3_{k}_v1.txt").read_text(encoding="utf-8")
              for k in ("extract", "expand", "classify")}
M3_KINDS = ["기능", "관리 작업", "부품", "화면 표시", "일반어", "기타"]
M3_KEEP = {"기능", "관리 작업", "미분류"}  # 규칙 ①: 기능·코스·모드·관리 작업만(미분류는 사용자 검토로 남김)
M3_FORMATS = {
    "classify": {"type": "json_schema", "name": "kinds", "strict": True,
                 "schema": {"type": "object", "required": ["items"], "additionalProperties": False, "properties": {"items": {
                     "type": "array", "items": {"type": "object", "required": ["name", "kind"], "additionalProperties": False,
                                                "properties": {"name": {"type": "string"}, "kind": {"type": "string", "enum": M3_KINDS}}}}}}},
    "extract": {"type": "json_schema", "name": "names", "strict": True,
                "schema": {"type": "object", "properties": {"names": {"type": "array", "items": {"type": "string"}}},
                           "required": ["names"], "additionalProperties": False}},
    "expand": {"type": "json_schema", "name": "terms", "strict": True,
               "schema": {"type": "object", "required": ["terms"], "additionalProperties": False, "properties": {"terms": {
                   "type": "array", "items": {"type": "object", "required": ["name", "expressions"], "additionalProperties": False,
                                              "properties": {"name": {"type": "string"},
                                                             "expressions": {"type": "array", "items": {"type": "string"}}}}}}}},
}


def batch_texts(texts: list[str], max_chars: int) -> list[str]:
    batches, cur = [], []
    for t in texts:
        if cur and len("\n".join(cur + [t])) > max_chars:
            batches.append("\n".join(cur))
            cur = []
        cur.append(t)
    return batches + (["\n".join(cur)] if cur else [])


def merge_names(lists: list[list[str]]) -> list[str]:
    out = []
    for names in lists:
        for n in (x.strip() for x in names):
            if 2 <= len(n) <= 20 and n not in out:
                out.append(n)
    return out


def parse_terms(raw: str, names: list[str], max_n: int = 5) -> dict[str, list[str]]:
    """받은 이름마다 표현 목록(이름과 띄어쓰기만 다른 말·중복·2~12자 밖은 뺌). 목록 밖 이름은 버리고, 빠진 이름은 빈 목록"""
    got = {t["name"].strip(): t["expressions"] for t in json.loads(raw)["terms"]}
    out = {}
    for name in names:
        exprs = []
        for e in (x.strip() for x in got.get(name, [])):
            if 2 <= len(e) <= 12 and e.replace(" ", "") != name.replace(" ", "") and e not in exprs:
                exprs.append(e)
        out[name] = exprs[:max_n]
    return out


def parse_kinds(raw: str, names: list[str]) -> dict[str, str]:
    got = {it["name"].strip(): it["kind"] for it in json.loads(raw)["items"]}
    return {n: got.get(n, "미분류") for n in names}


def keep_by_kind(terms: dict[str, list[str]], kinds: dict[str, str]) -> tuple[dict, dict]:
    kept = {n: e for n, e in terms.items() if kinds.get(n, "미분류") in M3_KEEP}
    return kept, {n: kinds[n] for n in terms if n not in kept}


def drop_wide_expressions(terms: dict[str, list[str]], max_names: int = 2) -> tuple[dict, dict]:
    """규칙 ③: 같은 표현이 기능 이름 3개 이상에 붙으면 그 표현을 모두에서 지운다(2개 이하는 둔다)"""
    owners = {}
    for n, exprs in terms.items():
        for e in exprs:
            owners.setdefault(e, []).append(n)
    wide = {e: ns for e, ns in owners.items() if len(ns) > max_names}
    return {n: [e for e in exprs if e not in wide] for n, exprs in terms.items()}, wide


def build_m3_messages(kind: str, model_name: str, material: str) -> list[dict]:
    body = material.replace("<", "〈").replace(">", "〉")
    return [{"role": "system", "content": M3_PROMPTS[kind]},
            {"role": "user", "content": f"모델: {model_name}\n<자료>\n{body}\n</자료>"}]


def m3_draft(names: dict[str, str]) -> None:
    import openai

    from app.core.config import get_settings
    from app.core.db import get_conn

    settings = get_settings()
    client = openai.OpenAI(api_key=settings.openai_api_key, timeout=60, max_retries=1)
    usage = {"input_tokens": 0, "output_tokens": 0}

    def call(kind: str, model_name: str, material: str) -> str:
        resp = client.responses.create(model=settings.openai_chat_model, reasoning={"effort": settings.reasoning_effort},
                                       max_output_tokens=4000, text={"format": M3_FORMATS[kind]},
                                       input=build_m3_messages(kind, model_name, material))
        for k in usage:
            usage[k] += getattr(resp.usage, k)
        return resp.output_text

    with get_conn() as conn:
        manuals = conn.execute("""SELECT d.id, dm.model_id FROM documents d JOIN document_models dm ON dm.doc_id = d.id
                                  WHERE d.doc_type = 'manual' ORDER BY d.id""").fetchall()
        texts = {doc: [t for (t,) in conn.execute("SELECT content FROM chunks WHERE doc_id = %s ORDER BY page, id", (doc,))]
                 for doc, _ in manuals}
    draft = {}
    for doc, model_id in manuals:
        found = merge_names([json.loads(call("extract", names[model_id], b))["names"] for b in batch_texts(texts[doc], 8000)])
        terms = {}
        for i in range(0, len(found), 40):  # 이름 40개씩 표현 만들기
            terms |= parse_terms(call("expand", names[model_id], "\n".join(found[i:i + 40])), found[i:i + 40])
        draft[model_id] = terms
        print(model_id, "기능 이름", len(found), flush=True)
    OUT.mkdir(exist_ok=True)
    path = OUT / "m3-terms-draft.json"  # 사용자 검토 전 초안
    path.write_text(json.dumps({"model": settings.openai_chat_model, "usage": usage, "terms": draft},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{path} usage={usage}")


def m3_reduce(names: dict[str, str]) -> None:
    """초안(m3-terms-draft.json)의 이름을 AI로 종류 분류 → 규칙 ① 이름 줄이기 → 규칙 ③ 겹친 표현 지우기 → 검토용 표"""
    import openai

    from app.core.config import get_settings

    settings = get_settings()
    client = openai.OpenAI(api_key=settings.openai_api_key, timeout=60, max_retries=1)
    draft = json.loads((OUT / "m3-terms-draft.json").read_text(encoding="utf-8"))["terms"]
    usage, result, lines = {"input_tokens": 0, "output_tokens": 0}, {}, []
    for model_id, terms in draft.items():
        all_names, kinds = list(terms), {}
        for i in range(0, len(all_names), 60):  # 이름 60개씩 분류
            part = all_names[i:i + 60]
            resp = client.responses.create(model=settings.openai_chat_model, reasoning={"effort": settings.reasoning_effort},
                                           max_output_tokens=4000, text={"format": M3_FORMATS["classify"]},
                                           input=build_m3_messages("classify", names[model_id], "\n".join(part)))
            for k in usage:
                usage[k] += getattr(resp.usage, k)
            kinds |= parse_kinds(resp.output_text, part)
        kept, removed = keep_by_kind(terms, kinds)
        kept, wide = drop_wide_expressions(kept)
        result[model_id] = {"kept": kept, "kinds": {n: kinds[n] for n in kept}, "removed": removed, "wide_expressions": wide}
        print(model_id, "남김", len(kept), "지움", len(removed), "겹쳐서 지운 표현", len(wide), flush=True)
    (OUT / "m3-terms-reduced.json").write_text(json.dumps({"usage": usage, "models": result}, ensure_ascii=False, indent=1),
                                               encoding="utf-8")
    write_m3_review(result, names)
    print(f"usage={usage}")


def m3_tidy(names: dict[str, str]) -> None:
    """기계적 정리: 띄어쓰기·끝 '기능'만 다른 이름 합치기 → 규칙 ③ 다시 적용 → 검토표 다시 만들기(AI 호출 없음)"""
    reduced = json.loads((OUT / "m3-terms-reduced.json").read_text(encoding="utf-8"))["models"]
    result = {}
    for model_id, r in reduced.items():
        merged, kinds, record = merge_variants(r["kept"], r["kinds"])
        kept, wide = drop_wide_expressions(merged)
        result[model_id] = {"kept": kept, "kinds": kinds, "removed": r["removed"], "merged": record, "wide_expressions": wide}
        print(model_id, "합치기 전", len(r["kept"]), "후", len(kept), "합친 묶음", len(record), "겹쳐서 지운 표현", len(wide), flush=True)
    (OUT / "m3-terms-tidy.json").write_text(json.dumps({"models": result}, ensure_ascii=False, indent=1), encoding="utf-8")
    write_m3_review(result, names)


M3_TERMS = Path(__file__).resolve().parent / "m3_terms.json"  # 확정 사전(기능 이름·평소 표현만, 설명서 본문 없음)


def m3_finalize(names: dict[str, str]) -> None:
    """확정: 검토한 목록(m3-terms-tidy.json) → 사용자 검토(m3_review.json) → 이름 끝 합치기 → 규칙 ③ → measure/m3_terms.json"""
    tidy = json.loads((OUT / "m3-terms-tidy.json").read_text(encoding="utf-8"))["models"]
    review = json.loads((Path(__file__).resolve().parent / "m3_review.json").read_text(encoding="utf-8"))
    final, result = {}, {}
    for model_id, r in tidy.items():
        reviewed = apply_review(r["kept"], review.get(model_id, {}))
        merged, kinds, record = merge_variants(reviewed, {n: r["kinds"][n] for n in reviewed})
        kept, wide = drop_wide_expressions(merged)
        final[model_id] = {"terms": kept, "merged": {n: r["merged"].get(n, []) + record.get(n, [])
                                                     for n in kept if r["merged"].get(n) or record.get(n)},
                           "wide_expressions": wide}
        result[model_id] = {"kept": kept, "kinds": kinds, "removed": r["removed"], "merged": final[model_id]["merged"],
                            "wide_expressions": wide}
        print(model_id, "검토 후", len(reviewed), "합친 뒤", len(kept), "표현", sum(len(e) for e in kept.values()),
              "새로 합친 묶음", len(record), "겹쳐서 지운 표현", len(wide), flush=True)
    M3_TERMS.write_text(json.dumps({"_note": "검색 개선 M3 확정 용어 사전(2026-11-10). 설명서만 보고 AI 생성 → 규칙 ①·③, 사용자 검토"
                                    "(measure/m3_review.json), 이름 끝 합치기. 질문 넓히기는 expand_query(규칙 ②)",
                                    "models": final}, ensure_ascii=False, indent=1), encoding="utf-8")
    write_m3_review(result, names)
    print(M3_TERMS)


def load_terms() -> dict[str, dict[str, list[str]]]:
    return {m: v["terms"] for m, v in json.loads(M3_TERMS.read_text(encoding="utf-8"))["models"].items()}


def write_m3_review(result: dict, names: dict[str, str]) -> None:
    """검토용 표: measure/out/m3-terms-reduced.md(모델별 표 + 합친·지운 기록)와 .csv(남길까·고칠 표현 칸)"""
    lines = []
    with (OUT / "m3-terms-reduced.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model_id", "기능 이름", "종류", "표현", "합친 이름", "남길까(O/X)", "고칠 표현"])
        for model_id, r in result.items():
            merged = r.get("merged", {})
            lines += [f"\n## {names[model_id]} (`{model_id}`) — 남김 {len(r['kept'])} / 지움 {len(r['removed'])}\n",
                      "| 기능 이름 | 종류 | 표현 | 합친 이름 |", "|---|---|---|---|"]
            for n, e in r["kept"].items():
                lines.append(f"| {n} | {r['kinds'][n]} | {' · '.join(e) or '-'} | {', '.join(merged.get(n, [])) or '-'} |")
                w.writerow([model_id, n, r["kinds"][n], " · ".join(e), ", ".join(merged.get(n, [])), "", ""])
            if r["wide_expressions"]:
                lines += ["", "겹쳐서 지운 표현(이름 3개 이상): " + "; ".join(f"{e} ({', '.join(ns)})" for e, ns in r["wide_expressions"].items())]
            lines += ["", "AI가 지운 이름: " + ", ".join(f"{n}({k})" for n, k in r["removed"].items())]
    (OUT / "m3-terms-reduced.md").write_text("# M3 용어 사전 줄인 목록 (사용자 검토용)\n" + "\n".join(lines) + "\n", encoding="utf-8")
    print(OUT / "m3-terms-reduced.csv")


M2_SAMPLE_DOCS = ["manual-lg-fx25", "manual-samsung-wd90h25", "manual-lg-sq06fa1wds", "guide-lg-drum-errors", "guide-samsung-drum-5c"]
M2_SEED = 20261110


def m2_sample(names: dict[str, str]) -> None:
    import openai

    from app.core.config import get_settings
    from app.core.db import get_conn

    settings = get_settings()
    client = openai.OpenAI(api_key=settings.openai_api_key, timeout=30, max_retries=1)
    with get_conn() as conn:
        rows = build_m1(conn, names)
        models = dict(conn.execute("SELECT doc_id, array_agg(model_id ORDER BY model_id) FROM document_models GROUP BY doc_id").fetchall())
        titles = dict(conn.execute("SELECT id, title FROM documents").fetchall())
    out, usage = [], {"input_tokens": 0, "output_tokens": 0}
    for r in sample_chunks(rows, M2_SAMPLE_DOCS, M2_SEED):
        content = r["text"].split("\n", 1)[1]
        resp = client.responses.create(model=settings.openai_chat_model, reasoning={"effort": settings.reasoning_effort},
                                       max_output_tokens=1000, text={"format": M2_FORMAT},
                                       input=build_m2_messages([names[m] for m in models[r["doc_id"]]], titles[r["doc_id"]], r["page"], content))
        for k in usage:
            usage[k] += getattr(resp.usage, k)
        kept, dropped = check_split(json.loads(resp.output_text), content, r["sub"])
        out.append({"chunk_id": r["chunk_id"], "doc_id": r["doc_id"], "page": r["page"], "title": r["title"], "sub": r["sub"],
                    "chunk": content, "questions": kept, "dropped": dropped})
    OUT.mkdir(exist_ok=True)
    path = OUT / "m2-sample.json"  # 조각 본문이 들어 있어 저장소 밖에만 둔다
    path.write_text(json.dumps({"model": settings.openai_chat_model, "reasoning": settings.reasoning_effort,
                                "usage": usage, "items": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{path} usage={usage}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("variant", choices=["m1", "m2", "m3"])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--reduce", action="store_true")
    ap.add_argument("--tidy", action="store_true")
    ap.add_argument("--finalize", action="store_true")
    args = ap.parse_args()

    from ingest.__main__ import load_env
    load_env()
    from app.catalog.registry import load_models
    from app.core.db import get_conn
    from app.retrieval.embeddings import embed_texts

    names = {m["id"]: m["display_name"] for m in load_models()}
    if args.variant == "m2":
        return m2_sample(names) if args.sample else print("M2 전체 생성은 시험 생성 검토 후에 만든다")
    if args.variant == "m3":
        if args.reduce:
            return m3_reduce(names)
        if args.tidy:
            return m3_tidy(names)
        if args.finalize:
            return m3_finalize(names)
        return m3_draft(names) if args.draft else print("M3는 초안(--draft)·줄이기(--reduce)만. 사용자 검토 후 질문 넓히기 함수를 만든다")
    with get_conn() as conn:
        rows = build_m1(conn, names)
        OUT.mkdir(exist_ok=True)
        out = OUT / "m1-titles.csv"  # 제목만(본문 없음)
        with out.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["doc_id", "page", "title"])
            w.writerows(sorted({(r["doc_id"], r["page"] or 0, r["title"]) for r in rows}, key=lambda x: (x[0], x[1])))
        print(f"조각 {len(rows)}개, 쪽별 제목 {out}")
        if not args.apply:
            return
        if conn.execute("SELECT count(*) FROM chunk_variants WHERE variant = 'm1_title'").fetchone()[0]:
            raise SystemExit("m1_title 행이 이미 있어 멈춤(지우기는 사용자 확인 후)")
        vectors = embed_texts([r["text"] for r in rows])
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO chunk_variants (chunk_id, variant, text, embedding) VALUES (%s, 'm1_title', %s, %s::vector)",
                            [(r["chunk_id"], r["text"], v) for r, v in zip(rows, vectors)])
        print(f"m1_title {len(rows)}행 넣음")


if __name__ == "__main__":
    main()
