// 근거 접기(2026-11-11 사용자 결정): 접힌 줄 라벨, 같은 출처끼리 묶기, 경고·공식 링크 중복 없애기.
// 화면 없이 시험할 수 있게 순수 함수로 둔다(tests/web/js/evidence.test.mjs). 객체가 아닌 근거(망가진 저장 항목)는 버린다
const valid = (citations) => (Array.isArray(citations) ? citations : []).filter((c) => c !== null && typeof c === "object");
const isManual = (c) => c.doc_type === "manual";

// 설명서는 쪽별, 가이드는 문서(제목)별 한 묶음. 순서는 인용이 처음 나온 순서
export function groupCitations(citations) {
  const groups = new Map();
  for (const c of valid(citations)) {
    const key = isManual(c) ? `manual:${c.page}` : `guide:${c.title}`;
    if (!groups.has(key)) groups.set(key, { doc_type: isManual(c) ? "manual" : "guide", page: c.page ?? null, title: String(c.title ?? ""), quotes: [] });
    groups.get(key).quotes.push(String(c.quote ?? ""));
  }
  return [...groups.values()];
}

// "근거 보기 · 사용설명서 38·50·72쪽 · 공식 해결 가이드 N개"(쪽은 중복 없이 오름차순)
export function evidenceLabel(citations) {
  const groups = groupCitations(citations);
  const pages = groups.filter((g) => g.doc_type === "manual" && Number.isFinite(g.page)).map((g) => g.page).sort((a, b) => a - b);
  const guides = groups.filter((g) => g.doc_type === "guide").length;
  return ["근거 보기", ...(pages.length ? [`사용설명서 ${pages.join("·")}쪽`] : []), ...(guides ? [`공식 해결 가이드 ${guides}개`] : [])].join(" · ");
}

export function warnings(citations) {
  return [...new Set(valid(citations).map((c) => c.warning).filter((w) => typeof w === "string" && w.trim()))];
}

export function offerText(citations) {
  const cs = valid(citations);
  const manual = cs.some(isManual), guide = cs.some((c) => !isManual(c));
  return manual && guide ? "공식 설명서·문서를 드릴까요?" : manual ? "공식 설명서를 드릴까요?" : "공식 문서를 드릴까요?";
}

// 버튼을 누르면 나오는 링크(URL 중복 없이). 설명서는 내려받기 페이지라 검색어(모델 코드)를 함께 알려 준다.
// "코드는 모델 선택 화면에서만"의 유일한 예외(2026-11-10 사용자 결정)
export function docLinks(citations, modelCodes) {
  const seen = new Set();
  return valid(citations).filter((c) => typeof c.url === "string" && c.url && !seen.has(c.url) && seen.add(c.url))
    .map((c) => ({ url: c.url, text: isManual(c) ? `공식 설명서 받기 (검색어: ${modelCodes.join("·")})` : `공식 문서 열기: ${c.title}` }));
}
