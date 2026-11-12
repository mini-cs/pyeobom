// 서버로 보낼 앞 대화(history). 질문은 가린 글, 답은 글자만 보낸다(근거·고쳐 쓴 질문은 보내지 않는다).
// 가린 질문은 원래 질문보다 길어질 수 있어(주소 → [주소]) 보낼 때만 서버 한도(app/ask/routes.py HistoryTurn.question)로 자른다.
// 서버는 글자(코드 포인트) 수로 재므로 반쪽 글자가 남지 않게 코드 포인트로 자른다. 저장된 턴은 바꾸지 않는다
export const HISTORY_QUESTION_MAX = 500;
const cut = (s) => (typeof s === "string" && s.length > HISTORY_QUESTION_MAX ? [...s].slice(0, HISTORY_QUESTION_MAX).join("") : s);

export function buildHistory(turns) {
  return turns.slice(-3).map((t) => ({ question: cut(t.question_masked), answer: t.answer }));
}

const norm = (s) => s.trim().replace(/\s+/g, " ");

export function shouldShowRewritten(questionMasked, rewritten) {
  if (!rewritten) return false;
  return norm(questionMasked) !== norm(rewritten);
}
