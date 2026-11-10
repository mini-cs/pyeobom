// 대화 저장(localStorage). 저장소 객체를 인자로 받아 시험할 수 있게 한다. 예외는 밖으로 던지지 않는다.
export const STORE_KEY = "pyeobom.conversations";
export const STORE_VERSION = 1;
export const LIMITS = { conversations: 20, turns: 30 };

const byRecent = (a, b) => (a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : 0);

export function loadConversations(storage) {
  try {
    const data = JSON.parse(storage.getItem(STORE_KEY));
    if (!data || data.version !== STORE_VERSION || !Array.isArray(data.conversations)) return [];
    return [...data.conversations].sort(byRecent);
  } catch {
    return [];
  }
}

function write(storage, conversations) {
  try {
    storage.setItem(STORE_KEY, JSON.stringify({ version: STORE_VERSION, conversations }));
    return true;
  } catch {
    return false;
  }
}

// 저장 직전에 다시 읽어, 다른 탭이 저장한 대화를 덮어쓰지 않는다.
export function saveConversation(storage, conversation) {
  try {
    const fresh = { ...conversation, turns: conversation.turns.slice(-LIMITS.turns) };
    const others = loadConversations(storage).filter((c) => c.id !== fresh.id);
    return write(storage, [fresh, ...others].sort(byRecent).slice(0, LIMITS.conversations));
  } catch {
    return false;
  }
}

export function deleteConversation(storage, id) {
  return write(storage, loadConversations(storage).filter((c) => c.id !== id));
}

export function deleteAllConversations(storage) {
  return write(storage, []);
}

// 서버 응답에서 저장할 6개 항목만 꺼낸다. 원래 질문(question)은 저장하지 않는다.
export function toStoredTurn(response) {
  if (!response || response.error_code) return null;
  const kind = response.reason === "other_brand" ? "other_brand" : response.found === true ? "answer" : "not_found";
  return {
    question_masked: response.question_masked,
    rewritten_question: response.rewritten_question ?? null,
    answer: response.answer,
    found: response.found === true,
    citations: response.citations ?? [],
    kind,
  };
}

export function makeTitle(questionMasked) {
  return Array.from(questionMasked).slice(0, 30).join("");
}
