// 대화 저장(localStorage). 저장소 객체를 인자로 받아 시험할 수 있게 한다. 예외는 밖으로 던지지 않는다.
export const STORE_KEY = "pyeobom.conversations";
export const STORE_VERSION = 1;
export const LIMITS = { conversations: 20, turns: 30 };

const byRecent = (a, b) => (a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : 0);

const isValid = (c) => c !== null && typeof c === "object" && typeof c.id === "string" && typeof c.updated_at === "string" && Array.isArray(c.turns);

// ok=false: 읽기 실패이거나 다른 버전 데이터가 있음 → 쓰면 그 데이터를 잃으므로 쓰지 않는다.
function readState(storage) {
  let raw;
  try {
    raw = storage.getItem(STORE_KEY);
  } catch {
    return { ok: false, list: [] };
  }
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    return { ok: true, list: [] }; // 읽을 수 없는 JSON은 복구 불가라 덮어써도 된다
  }
  if (data === null || typeof data !== "object") return { ok: true, list: [] };
  if (data.version !== STORE_VERSION) return { ok: false, list: [] };
  if (!Array.isArray(data.conversations)) return { ok: true, list: [] };
  return { ok: true, list: data.conversations.filter(isValid).sort(byRecent) };
}

export function loadConversations(storage) {
  return readState(storage).list;
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
    const { ok, list } = readState(storage);
    if (!ok) return false;
    const fresh = { ...conversation, turns: conversation.turns.slice(-LIMITS.turns) };
    const others = list.filter((c) => c.id !== fresh.id);
    return write(storage, [fresh, ...others].sort(byRecent).slice(0, LIMITS.conversations));
  } catch {
    return false;
  }
}

export function deleteConversation(storage, id) {
  const { ok, list } = readState(storage);
  return ok && write(storage, list.filter((c) => c.id !== id));
}

export function deleteAllConversations(storage) {
  return readState(storage).ok && write(storage, []);
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
