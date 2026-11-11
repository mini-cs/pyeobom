// 서버로 보낼 앞 대화(history). 질문은 가린 글, 답은 글자만 보낸다(근거·고쳐 쓴 질문은 보내지 않는다).
export function buildHistory(turns) {
  return turns.slice(-3).map((t) => ({ question: t.question_masked, answer: t.answer }));
}

const norm = (s) => s.trim().replace(/\s+/g, " ");

export function shouldShowRewritten(questionMasked, rewritten) {
  if (!rewritten) return false;
  return norm(questionMasked) !== norm(rewritten);
}
