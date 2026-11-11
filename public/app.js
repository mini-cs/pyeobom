// 펴봄 화면 전환: ① 랜딩 → ② 카테고리 → ③ 모델 → ④ 채팅(# 주소, 브라우저 뒤로 가기). API 글자는 textContent로만 넣는다(XSS 방지).
import { loadConversations, makeTitle, saveConversation, toStoredTurn } from "./js/store.js";
import { buildHistory, shouldShowRewritten } from "./js/history.js";
import { EXAMPLES } from "./js/examples.js";

const MAX_LEN = 500;
const NETWORK_ERROR = "일시적인 문제가 생겼어요. 잠시 후 다시 시도해 주세요";
const MODELS_ERROR = "모델 목록을 불러오지 못했어요. 새로고침해 주세요";
const APPLIANCES = { washer: "세탁기", aircon: "에어컨" };
const RECENT_LIMIT = { landing: 1, category: 3 };  // 설계 2절 ①·②, 계획 기본값 5

const $ = (id) => document.getElementById(id);
const ui = {
  topbar: $("topbar"), brand: $("brand"), newChat: $("new-chat"), tiles: $("tiles"), dots: $("tile-dots"),
  modelTitle: $("model-title"), modelCards: $("model-cards"), chatTitle: $("chat-title"),
  form: $("ask-form"), question: $("question"), counter: $("counter"), send: $("send"),
  formError: $("form-error"), pii: $("pii-note"), saveNote: $("save-note"), status: $("chat-status"),
  thread: $("thread"), suggestions: $("suggestions"),
};
const PLACEHOLDER = ui.question.placeholder;

let busy = false;
let renderId = 0;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function icon(name) {
  const span = el("span", `icon icon-${name}`);
  span.setAttribute("aria-hidden", "true");
  return span;
}

function link(text, href) {
  const a = el("a", "doc-link", text);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

function storage() {
  try { return window.localStorage; } catch { return null; }  // 쿠키 차단이면 접근만 해도 예외
}

const modelsReady = fetch("/api/models")
  .then((res) => { if (!res.ok) throw new Error(String(res.status)); return res.json(); })
  .catch(() => []);

// ── 주소 ──
function parseRoute(hash) {
  try {
    const [name, a, b] = hash.replace(/^#/, "").split("/").map(decodeURIComponent);
    if (name === "category") return { screen: "category" };
    if (name === "model" && APPLIANCES[a]) return { screen: "model", appliance: a };
    if (name === "chat" && a) return { screen: "chat", modelId: a, conversationId: b };
  } catch { /* 잘못된 % 표기는 랜딩으로 */ }
  return { screen: "landing" };
}

function show(name, focus) {
  for (const s of document.querySelectorAll(".screen")) s.hidden = s.dataset.screen !== name;
  ui.topbar.hidden = name === "landing";
  const chat = name === "chat";
  ui.brand.hidden = chat;
  ui.chatTitle.hidden = !chat;
  ui.newChat.hidden = !chat;
  if (focus) {
    window.scrollTo(0, 0);
    (chat ? ui.chatTitle : document.querySelector(`[data-screen="${name}"] h1`)).focus();
  }
}

// 화면은 바로 바꾸고, 모델 목록이 필요한 부분은 받은 뒤 채운다
async function render(focus) {
  const id = ++renderId;
  const route = parseRoute(location.hash);
  if (route.screen === "model") {
    ui.modelTitle.textContent = `${APPLIANCES[route.appliance]} 모델을 골라 주세요`;
    ui.modelCards.replaceChildren();
  }
  show(route.screen, focus);
  if (route.screen === "category") updateDots();
  const models = await modelsReady;
  if (id !== renderId) return;  // 그사이 다른 화면으로 옮겼으면 버린다
  if (route.screen === "landing" || route.screen === "category") {
    renderRecent($(`${route.screen}-recent`), RECENT_LIMIT[route.screen], models);
  } else if (route.screen === "model") {
    renderModelCards(route.appliance, models);
  } else {
    const model = models.find((m) => m.id === route.modelId);
    if (model) openChat(model, route.conversationId);
    else location.replace("#category");  // 없는 모델 주소
  }
}

// ── 최근 대화 카드 ──
function formatDate(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("ko-KR", { month: "long", day: "numeric" });
}

function renderRecent(section, limit, models) {
  const names = new Map(models.map((m) => [m.id, m.name]));  // 모델 코드는 모델 선택 화면에서만
  const list = loadConversations(storage()).filter((c) => names.has(c.model_id)).slice(0, limit);
  section.hidden = list.length === 0;
  section.querySelector("ul").replaceChildren(...list.map((c) => {
    const a = el("a", "conv-card");
    a.href = `#chat/${encodeURIComponent(c.model_id)}/${encodeURIComponent(c.id)}`;
    const text = el("span", "card-text");
    const date = formatDate(c.updated_at);
    text.append(el("span", "card-title", String(c.title ?? "")),
      el("span", "card-meta", date ? `${names.get(c.model_id)} · ${date}` : names.get(c.model_id)));
    a.append(text, icon("chevron"));
    const li = el("li");
    li.append(a);
    return li;
  }));
}

// ── 카테고리 타일: 화살표 키로 옆 타일, 점은 넘긴 위치 ──
function pageCount() {
  return Math.max(1, Math.ceil(ui.tiles.scrollWidth / ui.tiles.clientWidth));
}

function updateDots() {
  const pages = pageCount();
  const max = ui.tiles.scrollWidth - ui.tiles.clientWidth;
  const active = max > 0 ? Math.round((ui.tiles.scrollLeft / max) * (pages - 1)) : 0;
  if (ui.dots.childElementCount !== pages) {
    ui.dots.replaceChildren(...Array.from({ length: pages }, (_, i) => {
      const b = el("button", "dot");
      b.type = "button";
      b.setAttribute("aria-label", `가전 목록 ${i + 1}쪽`);
      b.addEventListener("click", () => {
        const end = ui.tiles.scrollWidth - ui.tiles.clientWidth;
        ui.tiles.scrollTo({ left: (end * i) / Math.max(1, pageCount() - 1) });
      });
      return b;
    }));
  }
  ui.dots.hidden = pages < 2;
  [...ui.dots.children].forEach((b, i) => b.setAttribute("aria-current", String(i === active)));
}

// 옆으로 넘기는 줄(카테고리 타일·추천 카드)은 화살표 키로 옆 항목에 포커스(가이드 6절 5)
function arrowKeys(box, selector) {
  box.addEventListener("keydown", (e) => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (!step) return;
    const items = [...box.querySelectorAll(selector)];
    const next = items[items.indexOf(document.activeElement) + step];
    if (next) {
      e.preventDefault();
      next.focus();
    }
  });
}
arrowKeys(ui.tiles, ".tile");
arrowKeys(ui.suggestions, ".suggestion");
ui.tiles.addEventListener("click", (e) => {
  const tile = e.target.closest(".tile");
  if (tile && tile.dataset.appliance) location.hash = `#model/${tile.dataset.appliance}`;  // "곧 추가"는 이동하지 않음
});
ui.tiles.addEventListener("scroll", updateDots, { passive: true });
window.addEventListener("resize", () => { if (!ui.tiles.closest(".screen").hidden) updateDots(); });

// ── 모델 카드 ──
function renderModelCards(appliance, models) {
  if (!models.length) {
    ui.modelCards.replaceChildren(el("li", "empty", MODELS_ERROR));
    return;
  }
  ui.modelCards.replaceChildren(...models.filter((m) => m.appliance === appliance).map((m) => {
    const a = el("a", "model-card");
    a.href = `#chat/${encodeURIComponent(m.id)}`;
    const img = el("img", "model-illust");
    img.src = `/images/models/${encodeURIComponent(m.id)}.svg`;
    img.alt = "";  // 이름이 바로 옆에 있어 그림은 꾸밈(AI 일러스트라 설명을 읽어 줄 필요가 없음)
    const text = el("span", "card-text");
    // 코드 하나는 줄을 바꾸지 않고, 코드 사이(" · " 뒤)에서만 줄이 바뀐다
    const codes = el("span", "card-meta model-codes");
    m.model_codes.forEach((code, i) => codes.append(...(i ? [" · "] : []), el("span", "model-code", code)));
    const hint = el("span", "card-meta");
    hint.append(el("strong", null, "모델명 찾는 법 "), m.model_name_hint);
    text.append(el("span", "card-title", m.name), codes, hint);
    a.append(img, text, icon("chevron"));
    const li = el("li");
    li.append(a);
    return li;
  }));
}

// ── ④ 채팅(설계 2절 ④·5절): 대화 하나 = 모델 하나. 저장은 가린 질문만(toStoredTurn) ──
// entries: 화면의 턴. { question, history, pending } → 응답 뒤 { turn(저장 형식), officialUrl } 또는 { error }
// 대화를 열거나 새로 시작할 때마다 새 chat 객체를 만든다. 기다리던 답은 보낸 때의 객체(대화)에 저장한다
let chat = { model: null, conv: null, entries: [] };

const chatHash = (modelId, convId) => `#chat/${encodeURIComponent(modelId)}` + (convId ? `/${encodeURIComponent(convId)}` : "");

function openChat(model, conversationId) {
  ui.chatTitle.textContent = model.short_name ?? model.name;  // 위쪽 막대 한 줄(2026-11-10 사용자 결정)
  // 같은 대화 주소면 그대로 둔다. 대화 id가 없는 주소(모델 카드·새 대화)는 언제나 새 대화(2026-11-10 사용자 결정)
  if (conversationId && chat.model?.id === model.id && conversationId === chat.conv?.id) return;
  const saved = conversationId
    ? loadConversations(storage()).find((c) => c.id === conversationId && c.model_id === model.id)
    : null;  // 없는 id이거나 다른 모델의 대화면 새 대화(다른 모델의 앞 대화가 섞이지 않게)
  resetChat(model, saved ?? null);
}

// 저장소의 턴은 그리기 전에 모양을 맞춘다(망가진 항목 때문에 화면이 멈추지 않게)
function entriesFrom(turns) {
  return turns
    .filter((t) => t && typeof t.question_masked === "string" && typeof t.answer === "string")
    .map((t) => ({
      ...t,
      rewritten_question: typeof t.rewritten_question === "string" ? t.rewritten_question : null,
      citations: Array.isArray(t.citations) ? t.citations.filter((c) => c !== null && typeof c === "object") : [],
    }))
    .map((t) => ({ question: t.question_masked, turn: t }));
}

function resetChat(model, conv) {
  chat = { model, conv, entries: entriesFrom(conv ? conv.turns : []) };
  setBusy(false);  // 기다리던 답은 원래 대화에 저장만 되고 이 화면은 막지 않는다
  ui.question.value = "";
  updateCounter();
  showFormError("");
  ui.pii.hidden = true;
  ui.saveNote.hidden = true;
  ui.status.textContent = "";
  renderSuggestions();
  renderChat();
}

// 화면은 여기서 바로 비우고, 주소는 pushState로만 바꾼다(hashchange가 늦게 와서 그사이 보낸 질문까지 비우지 않게).
// 뒤로 가기로 앞 대화 주소에 돌아가면 hashchange가 와서 그 대화를 다시 연다
ui.newChat.addEventListener("click", () => {
  const target = chatHash(chat.model.id);
  resetChat(chat.model, null);
  if (location.hash !== target) history.pushState(null, "", target);
});

function renderSuggestions() {
  ui.suggestions.replaceChildren(...(EXAMPLES[chat.model.id] || []).map(({ question, hint }) => {
    const b = el("button", "suggestion");
    b.type = "button";
    b.append(el("strong", null, question), el("span", "muted", hint));
    b.addEventListener("click", () => {
      ui.question.focus();  // 카드가 사라져도 키보드 포커스가 입력창에 남게
      ask(question);
    });
    return b;
  }));
}

function updateCounter() {
  const left = MAX_LEN - ui.question.value.length;
  ui.counter.textContent = `${left}자 남음`;
  ui.counter.classList.toggle("is-low", left <= 50);
  ui.question.style.height = "auto";  // 글이 길어지면 입력창이 늘어난다(최대 높이는 CSS)
  ui.question.style.height = `${ui.question.scrollHeight}px`;
}

function showFormError(message) {
  ui.formError.textContent = message;
  ui.formError.hidden = !message;
}

function setBusy(on) {
  busy = on;
  ui.send.disabled = on;
}

function renderEvidence(c) {
  const box = el("div", "evidence");
  if (c.doc_type === "manual") {
    box.append(el("p", "evidence-label", `사용설명서 ${c.page}쪽`), el("p", "evidence-title", c.title));
  } else {
    box.append(el("p", "evidence-label", `공식 해결 가이드: ${c.title}`));
  }
  box.append(el("blockquote", null, c.quote));
  // 설명서는 내려받기 페이지라 1차처럼 검색어(모델 코드)를 함께 알려 준다.
  // "코드는 모델 선택 화면에서만"의 유일한 예외(2026-11-10 사용자 결정)
  box.append(c.doc_type === "manual"
    ? link(`공식 설명서 받기 (검색어: ${chat.model.model_codes.join("·")})`, c.url)
    : link("공식 문서 열기", c.url));
  if (c.warning) box.append(notice("info", "참고", c.warning));  // 가이드 6절 8: 근거 박스 맨 아래
  return box;
}

function notice(name, label, text) {
  const p = el("p", "notice");
  const body = el("span");
  body.append(el("strong", null, label), " ", el("span", null, text));
  p.append(icon(name), body);
  return p;
}

const STATES = { answer: "answer", not_found: "not-found", other_brand: "other-brand" };

function answerBody(entry) {
  const t = entry.turn;
  const body = el("div", "answer-body");
  if (shouldShowRewritten(t.question_masked, t.rewritten_question)) {
    body.append(el("p", "rewritten", `'${t.rewritten_question}'로 찾았어요`));
  }
  if (t.kind === "other_brand") {  // 서버 답 그대로 + 앱 안에서 모델을 다시 고르게(2026-11-10 사용자 결정)
    const again = el("button", "pill", "모델 다시 고르기");
    again.type = "button";
    again.addEventListener("click", () => { location.hash = "#category"; });
    body.append(notice("info", "모델 안내", t.answer), again);
  } else {
    body.append(el("p", "answer", t.answer));
    if (t.kind === "answer") (Array.isArray(t.citations) ? t.citations : []).forEach((c) => body.append(renderEvidence(c)));
    else body.append(link("공식 고객센터에서 찾아보기", entry.officialUrl ?? chat.model.official_url));  // 저장한 턴에는 official_url이 없다
  }
  return body;
}

function renderEntry(entry, index, latest) {
  const turn = el("article", "turn");
  turn.append(el("p", "bubble", entry.turn ? entry.turn.question_masked : entry.question));
  if (entry.pending) {
    turn.dataset.state = "loading";
    const box = el("div", "loading");
    box.append(el("span", null, "설명서를 펴 보는 중…"), el("div", "progress"));
    turn.append(box);
  } else if (entry.error) {
    turn.dataset.state = "error";
    const card = el("div", "error-card");
    card.setAttribute("role", "alert");
    const line = el("p");
    line.append(icon("alert"), el("span", null, entry.error.message));
    card.append(line);
    if (entry.error.retry) {
      const b = el("button", "pill", "다시 시도");
      b.type = "button";
      b.addEventListener("click", () => {
        ui.question.focus();
        ask(entry.question, entry);
      });
      card.append(b);
    }
    turn.append(card);
  } else {
    turn.dataset.state = STATES[entry.turn.kind] ?? "answer";
    const body = answerBody(entry);
    if (!latest) {  // 이전 답은 본문과 근거를 함께 한 줄로 접는다(계획 기본값 11)
      const n = Array.isArray(entry.turn.citations) ? entry.turn.citations.length : 0;
      const fold = el("button", "fold");
      fold.type = "button";
      fold.append(el("span", null, n ? `이전 답 · 근거 ${n}개` : "이전 답 · 근거 없음"), icon("chevron-down"));
      body.id = `turn-body-${index}`;
      body.hidden = true;
      fold.setAttribute("aria-controls", body.id);
      fold.setAttribute("aria-expanded", "false");
      fold.addEventListener("click", () => {
        body.hidden = !body.hidden;
        fold.setAttribute("aria-expanded", String(!body.hidden));
      });
      turn.append(fold);
    }
    turn.append(body);
  }
  return turn;
}

function renderChat() {
  const { entries } = chat;
  ui.thread.replaceChildren(...entries.map((e, i) => renderEntry(e, i, i === entries.length - 1)));
  ui.suggestions.hidden = entries.length > 0;
  ui.question.placeholder = entries.some((e) => e.turn) ? "이어서 물어보세요" : PLACEHOLDER;
  updateCounter();  // 안내 문구가 바뀌어도 입력창 높이를 다시 맞춘다
  ui.thread.lastElementChild?.scrollIntoView({ block: "start" });
}

const newId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

// 첫 정상 응답에서 대화를 만들고(계획 기본값 4), 응답마다 턴을 더해 저장한다. 실패해도 화면은 계속 간다(설계 5절)
// state는 질문을 보낸 때의 대화. 지금 보고 있는 대화가 아니면 저장만 하고 화면·주소는 건드리지 않는다
function saveTurn(state, turn) {
  const now = new Date().toISOString();
  const current = state === chat;
  if (!state.conv) {
    state.conv = { id: newId(), model_id: state.model.id, title: makeTitle(turn.question_masked), created_at: now, updated_at: now, turns: [] };
    if (current && location.hash === chatHash(state.model.id)) history.replaceState(null, "", chatHash(state.model.id, state.conv.id));
  }
  // 저장 직전에 같은 대화를 다시 읽어 그 턴들 뒤에 이어 붙인다. 그사이 같은 대화를 다시 연 화면이
  // 저장한 턴(또는 늦게 온 답)을 메모리의 옛 사본으로 덮어쓰지 않게. 개수 한도는 saveConversation(store.js)이 지킨다.
  // 이 대화의 앞 저장이 실패했으면 저장소 사본이 메모리보다 오래됐으므로 메모리 쪽을 쓴다
  const stored = state.unsaved ? null : loadConversations(storage()).find((c) => c.id === state.conv.id);
  const base = stored ?? state.conv;
  state.conv = { ...base, turns: [...base.turns, turn], updated_at: now };
  state.unsaved = !saveConversation(storage(), state.conv);
  // 안내는 요소 하나라 여러 번 실패해도 대화당 하나만 보인다. 새 대화(resetChat)에서 끈다
  if (state.unsaved && current) ui.saveNote.hidden = false;
}

const isAnswer = (d) => d && !d.error_code && typeof d.answer === "string" && typeof d.question_masked === "string";

async function ask(text, retryOf) {
  if (busy || !chat.model) return;
  const question = text.trim();
  if (!question) return showFormError("질문을 입력해 주세요");
  if (question.length > MAX_LEN) return showFormError(`질문은 ${MAX_LEN}자 이내로 입력해 주세요`);
  showFormError("");
  ui.pii.hidden = true;  // 이전 질문의 안내가 남지 않게
  // 오류 턴은 앞 대화에도 화면에도 남기지 않는다(계획 기본값 1). 다시 시도는 같은 질문·같은 history
  const prev = retryOf ? retryOf.history : buildHistory(chat.entries.filter((e) => e.turn).map((e) => e.turn));
  const entry = { question, history: prev, pending: true };
  chat.entries = [...chat.entries.filter((e) => !e.error), entry];
  if (!retryOf) {
    ui.question.value = "";
    updateCounter();
  }
  setBusy(true);
  ui.status.textContent = "설명서를 펴 보는 중…";
  renderChat();
  const state = chat;
  const { model } = state;
  let res = null;
  let data = null;
  try {
    const body = { model_id: model.id, question, ...(prev.length ? { history: prev } : {}) };  // 앞 대화가 없으면 보내지 않음
    res = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    data = await res.json().catch(() => null);
  } catch { /* 네트워크 오류는 아래에서 오류 카드로 */ }
  entry.pending = false;
  const answered = res?.ok && isAnswer(data);
  if (answered) {
    entry.turn = toStoredTurn(data);
    entry.officialUrl = data.official_url;
    saveTurn(state, entry.turn);  // 그사이 새 대화·다른 대화로 옮겼어도 보낸 대화에 저장한다
    // 화면의 대화가 같은 대화면(다시 연 사본 포함) 저장된 턴으로 맞춘다. 방금 답은 entry를 그대로 써서
    // 응답의 official_url을 지키고, 그 화면에서 기다리는 질문·오류 카드는 뒤에 남긴다
    if (chat.conv?.id === state.conv.id) {
      const turns = state.conv.turns;
      const last = state === chat ? [entry] : entriesFrom(turns.slice(-1));
      chat.conv = state.conv;
      chat.entries = [...entriesFrom(turns.slice(0, -1)), ...last, ...chat.entries.filter((e) => e.pending || e.error)];
      if (state !== chat) renderChat();
    }
  }
  if (state !== chat) return;  // 그 밖의 화면 처리는 지금 보고 있는 대화일 때만
  if (answered) {
    ui.pii.hidden = !data.pii_masked;
    ui.status.textContent = "답이 도착했어요";
  } else {
    // 입력 오류는 고쳐서 다시 보내면 되고, 그 밖의 오류는 같은 질문으로 다시 시도한다
    const inputError = ["EMPTY_QUESTION", "QUESTION_TOO_LONG", "INVALID_MODEL", "INVALID_REQUEST"].includes(data?.error_code);
    entry.error = { message: data?.message || NETWORK_ERROR, retry: !inputError };
    if (inputError && !ui.question.value) {
      ui.question.value = question;
      updateCounter();
    }
    ui.status.textContent = "";  // 오류 카드는 role="alert"로 알린다
  }
  setBusy(false);
  renderChat();
}

ui.question.addEventListener("input", updateCounter);
ui.question.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {  // 한글 조합 중 Enter는 무시
    e.preventDefault();
    ask(ui.question.value);
  }
});
ui.form.addEventListener("submit", (e) => {
  e.preventDefault();
  ask(ui.question.value);
});

// 처음 열면 # 부분과 상관없이 랜딩(계획 기본값 3). 주소의 #도 지워 뒤로 가기가 랜딩으로 오게 한다
history.replaceState(null, "", location.pathname + location.search);
window.addEventListener("hashchange", () => render(true));
render(false);
