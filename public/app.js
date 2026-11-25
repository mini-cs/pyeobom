// 펴봄 화면 전환: ① 랜딩 → ② 카테고리 → ③ 모델 → ④ 채팅(# 주소, 브라우저 뒤로 가기), ☰ ⑤ 지난 대화 서랍. API 글자는 textContent로만 넣는다(XSS 방지).
import { deleteAllConversations, deleteConversation, loadConversations, makeTitle, saveConversation, toStoredTurn } from "./js/store.js";
import { buildHistory, shouldShowRewritten } from "./js/history.js";
import { EXAMPLES } from "./js/examples.js";
import { wheelToScroll } from "./js/wheel.js";
import { docLinks, evidenceLabel, groupCitations, offerText, warnings } from "./js/evidence.js";
import { parentHash } from "./js/nav.js";
import { findExistingModel, LOGIN_REQUIRED, requestErrorMessage, requestRow, UNAVAILABLE, validateRequest } from "./js/request.js";
import { initAuth, isOtpCode } from "./js/auth.js";

const MAX_LEN = 500;
const NETWORK_ERROR = "일시적인 문제가 생겼어요. 잠시 후 다시 시도해 주세요";
const MODELS_ERROR = "모델 목록을 불러오지 못했어요. 새로고침해 주세요";
const APPLIANCES = { washer: "세탁기", dryer: "건조기", aircon: "에어컨" };
const RECENT_LIMIT = { landing: 1, category: 3 };  // 설계 2절 ①·②, 계획 기본값 5

const $ = (id) => document.getElementById(id);
const ui = {
  topbar: $("topbar"), menu: $("drawer-open"), brand: $("brand"), newChat: $("new-chat"), tiles: $("tiles"), dots: $("tile-dots"),
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
    if (name === "request" && APPLIANCES[a]) return { screen: "request", appliance: a };
    if (name === "chat" && a) return { screen: "chat", modelId: a, conversationId: b };
  } catch { /* 잘못된 % 표기는 랜딩으로 */ }
  return { screen: "landing" };
}

const heading = (name) => (name === "chat" ? ui.chatTitle : document.querySelector(`[data-screen="${name}"] h1`));

function show(name, focus) {
  for (const s of document.querySelectorAll(".screen")) s.hidden = s.dataset.screen !== name;
  ui.topbar.hidden = name === "landing";
  const chat = name === "chat";
  ui.brand.hidden = chat;
  ui.chatTitle.hidden = !chat;
  ui.newChat.hidden = !chat;
  if (focus) {
    window.scrollTo(0, 0);
    heading(name).focus();
  }
}

// 화면은 바로 바꾸고, 모델 목록이 필요한 부분은 받은 뒤 채운다
async function render(focus) {
  const id = ++renderId;
  const route = parseRoute(location.hash);
  if (route.screen === "model") {
    ui.modelTitle.textContent = `${APPLIANCES[route.appliance]} 모델을 골라 주세요`;
    ui.modelCards.replaceChildren();
    $("no-model-error").hidden = true;
  }
  if (route.screen === "request") prepareRequest(route.appliance);
  show(route.screen, focus);
  if (route.screen === "category") updateDots();
  const models = await modelsReady;
  if (id !== renderId) return;  // 그사이 다른 화면으로 옮겼으면 버린다
  if (route.screen === "landing" || route.screen === "category") {
    renderRecent($(`${route.screen}-recent`), RECENT_LIMIT[route.screen], models);
  } else if (route.screen === "model") {
    renderModelCards(route.appliance, models);
  } else if (route.screen === "request") {
    showRequestHint(route.appliance, models);
    requireLogin(location.hash);
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

// 목록에 있는 모델의 대화만, 최신순(깨진 링크 방지). 모델 코드는 모델 선택 화면에서만이라 이름은 name
function knownConversations(models) {
  const names = new Map(models.map((m) => [m.id, m.name]));
  return loadConversations(storage()).filter((c) => names.has(c.model_id)).map((c) => ({ c, name: names.get(c.model_id) }));
}

function convCard({ c, name }) {
  const a = el("a", "conv-card");
  a.href = `#chat/${encodeURIComponent(c.model_id)}/${encodeURIComponent(c.id)}`;
  const text = el("span", "card-text");
  const date = formatDate(c.updated_at);
  const meta = el("span", "card-meta", name);
  if (date) meta.append(" · ", el("span", "card-date", date));  // 날짜는 "11월 / 11일"로 나뉘지 않게 한 덩어리
  text.append(el("span", "card-title", String(c.title ?? "")), meta);
  a.append(text, icon("chevron"));
  return a;
}

function renderRecent(section, limit, models) {
  const list = knownConversations(models).slice(0, limit);
  section.hidden = list.length === 0;
  section.querySelector("ul").replaceChildren(...list.map((item) => {
    const li = el("li");
    li.append(convCard(item));
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
// 마우스 세로 휠로도 옆으로 넘긴다. 휠이 조금씩 여러 번 들어와 바로 이동(instant)이 자연스럽고 동작 줄이기와도 맞다
function wheelScroll(box) {
  box.addEventListener("wheel", (e) => {
    const left = wheelToScroll(e, box);
    if (!left) return;
    e.preventDefault();
    box.scrollBy({ left, behavior: "instant" });
  }, { passive: false });
}
// 아래 고정 입력창 높이를 --composer-h로 알려, 스크롤·포커스 이동 때 그 높이만큼 여백을 둔다(styles.css html, WCAG 2.2 2.4.11).
// 채팅이 아닌 화면에서는 입력창이 숨어 0이 된다
new ResizeObserver(() => document.documentElement.style.setProperty("--composer-h", `${ui.form.offsetHeight}px`)).observe(ui.form);

for (const [box, selector] of [[ui.tiles, ".tile"], [ui.suggestions, ".suggestion"]]) {
  arrowKeys(box, selector);
  wheelScroll(box);
}
ui.tiles.addEventListener("click", (e) => {
  const tile = e.target.closest(".tile");
  if (tile && tile.dataset.appliance) location.hash = `#model/${tile.dataset.appliance}`;  // "더 추가 예정"은 이동하지 않음
});
ui.tiles.addEventListener("scroll", updateDots, { passive: true });
window.addEventListener("resize", () => { if (!ui.tiles.closest(".screen").hidden) updateDots(); });

// ── 모델 카드 ──
function renderModelCards(appliance, models) {
  const mine = models.filter((m) => m.appliance === appliance);
  $("ai-note").hidden = mine.length === 0;  // 그림이 없으면 그림 안내도 없다
  if (!models.length) {
    ui.modelCards.replaceChildren(el("li", "empty", MODELS_ERROR));
    return;
  }
  if (!mine.length) {  // 건조기처럼 아직 모델이 없는 종류: 아래 "내 모델이 없어요"로 요청한다
    ui.modelCards.replaceChildren(el("li", "empty", `아직 등록된 ${APPLIANCES[appliance]} 모델이 없어요.`));
    return;
  }
  ui.modelCards.replaceChildren(...mine.map((m) => {
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
  if (conversationId && chat.model?.id === model.id && conversationId === chat.conv?.id) {
    updateCounter();  // 숨은 채 답이 와서 renderChat이 높이를 0으로 잰 경우가 있어 보이는 지금 다시 잰다
    return;
  }
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
  chat = { model, conv, entries: entriesFrom(conv ? conv.turns : []), saved: !!conv };  // saved: 저장소에 있었던 대화
  setBusy(false);  // 기다리던 답은 원래 대화에 저장만 되고 이 화면은 막지 않는다
  ui.question.value = "";
  updateCounter();
  showFormError("");
  ui.pii.hidden = true;
  ui.saveNote.hidden = true;
  ui.status.textContent = "";
  renderSuggestions();
  renderChat(false);
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
  // 꺼지는 버튼에 있던 키보드 포커스는 body로 떨어진다. 입력창으로 옮겨 둔다(계획 3 최종 검토 M2)
  if (on && document.activeElement === ui.send) ui.question.focus();
  ui.send.disabled = on;
}

// 누르면 target을 펼치고 접는 한 줄(이전 답 접기·근거 접기 공용)
function foldButton(text, target) {
  const fold = el("button", "fold");
  fold.type = "button";
  fold.append(el("span", null, text), icon("chevron-down"));
  fold.setAttribute("aria-controls", target.id);
  fold.setAttribute("aria-expanded", "false");
  fold.addEventListener("click", () => {
    target.hidden = !target.hidden;
    fold.setAttribute("aria-expanded", String(!target.hidden));
  });
  return fold;
}

// 같은 출처(설명서 쪽·가이드 문서) 한 상자: 라벨·제목·인용들만, 링크는 없다.
// 인용은 원문이 "•"로 시작하는 일이 많아 목록 기호를 붙이지 않고 인용마다 blockquote(원문 그대로, 간격으로 구분)
function renderGroup(g) {
  const box = el("div", "evidence");
  if (g.doc_type === "manual") box.append(el("p", "evidence-label", `사용설명서 ${g.page}쪽`), el("p", "evidence-title", g.title));
  else box.append(el("p", "evidence-label", `공식 해결 가이드: ${g.title}`));
  box.append(...g.quotes.map((q) => el("blockquote", null, q)));
  return box;
}

let evidenceSeq = 0;  // 근거 묶음 id(aria-controls)용. 다시 그릴 때마다 새 번호

// 근거 접기(2026-11-11 사용자 결정, 가이드 6절 7·8): 공용 가이드 경고 → 접힌 한 줄 → 회색 "드릴까요?" 버튼 하나
function renderCitations(body, citations) {
  const groups = groupCitations(citations);
  if (!groups.length) return;
  for (const w of warnings(citations)) body.append(notice("info", "참고", w));  // 경고는 접지 않는다
  const list = el("div", "evidence-list");
  list.id = `evidence-${++evidenceSeq}`;
  list.hidden = true;
  list.append(...groups.map(renderGroup));
  body.append(foldButton(evidenceLabel(citations), list), list);
  const links = docLinks(citations, chat.model.model_codes);
  if (!links.length) return;
  const offer = el("button", "offer");
  offer.type = "button";
  offer.append(icon("file"), el("span", null, offerText(citations)));
  offer.addEventListener("click", () => {
    const box = el("div", "doc-links");
    box.append(...links.map(({ text, url }) => {
      const row = el("p", "doc-link-row");
      row.append(icon("file"), link(text, url));
      return row;
    }));
    offer.replaceWith(box);
    box.querySelector("a").focus();  // 버튼이 사라지므로 포커스는 첫 링크로
  });
  body.append(offer);
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
    if (t.kind === "answer") renderCitations(body, t.citations);
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
      body.id = `turn-body-${index}`;
      body.hidden = true;
      turn.append(foldButton(n ? `이전 답 · 근거 ${n}개` : "이전 답 · 근거 없음", body));
    }
    turn.append(body);
  }
  return turn;
}

// 다시 그리면 목록 안 요소가 새로 만들어져 키보드 포커스가 body로 떨어진다(계획 3 최종 검토 M2).
// 몇 번째 턴의 어떤 줄인지 기억해 두었다가 같은 줄 → 그 턴의 이전 답 접기 줄 → 입력창 순서로 돌려준다
function focusSpot() {
  const a = document.activeElement;
  const turn = a?.closest(".turn");
  if (!turn || turn.parentElement !== ui.thread) return null;
  const inBody = !!a.closest(".answer-body");
  const sel = a.tagName + [...a.classList].map((c) => `.${CSS.escape(c)}`).join("");
  const scope = inBody ? a.closest(".answer-body") : turn;
  return { index: [...ui.thread.children].indexOf(turn), inBody, sel, nth: [...scope.querySelectorAll(sel)].indexOf(a) };
}

function restoreFocus(spot) {
  const turn = ui.thread.children[spot.index];
  const scope = spot.inBody ? turn?.querySelector(".answer-body") : turn;
  const same = scope?.querySelectorAll(spot.sel)[spot.nth];
  const fold = turn?.querySelector(":scope > .fold");
  const target = [same, fold, ui.question].find((e) => e && e.getClientRects().length);  // 숨겨진 요소는 건너뜀
  target?.focus({ preventScroll: true });  // 새 답으로 옮긴 스크롤은 그대로
}

function renderChat(keepFocus = true) {
  const { entries } = chat;
  const spot = keepFocus ? focusSpot() : null;  // 다른 대화를 여는 resetChat은 돌려주지 않는다
  ui.thread.replaceChildren(...entries.map((e, i) => renderEntry(e, i, i === entries.length - 1)));
  ui.suggestions.hidden = entries.length > 0;
  ui.question.placeholder = entries.some((e) => e.turn) ? "이어서 물어보세요" : PLACEHOLDER;
  updateCounter();  // 안내 문구가 바뀌어도 입력창 높이를 다시 맞춘다
  ui.thread.lastElementChild?.scrollIntoView({ block: "start" });
  if (spot) restoreFocus(spot);
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
  const stored = loadConversations(storage()).find((c) => c.id === state.conv.id);
  const base = state.unsaved || !stored ? state.conv : stored;
  state.conv = { ...base, turns: [...base.turns, turn], updated_at: now };
  // 한 번이라도 저장된 대화가 저장소에 없으면 그사이 지운 것이다(서랍·다른 탭). 늦은 답으로 되살리지 않는다
  state.unsaved = (state.saved && !stored) || !saveConversation(storage(), state.conv);
  if (!state.unsaved) state.saved = true;
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

// ── ⑤ 지난 대화 서랍(설계 2절 ⑤): 카드·대화마다 삭제·전체 삭제(화면 안 확인 단계) ──
const drawer = {
  box: $("drawer"), title: $("drawer-title"), list: $("drawer-list"), empty: $("drawer-empty"), error: $("drawer-error"),
  all: $("delete-all"), confirm: $("delete-confirm"), confirmText: $("delete-confirm-text"), cancel: $("delete-cancel"),
  back: $("drawer-back"),
};
let drawerModels = [];
let closedByLink = false;  // 서랍 안 링크(대화 카드·새 대화)로 닫혔는지

function renderDrawer() {
  const list = knownConversations(drawerModels);
  drawer.list.replaceChildren(...list.map((item) => {
    const del = el("button", "text-button", "지우기");
    del.type = "button";
    del.setAttribute("aria-label", `'${String(item.c.title ?? "")}' 대화 지우기`);
    del.addEventListener("click", () => deleteOne(item.c.id, del));
    const li = el("li", "drawer-item");
    li.append(convCard(item), del);
    return li;
  }));
  drawer.empty.hidden = list.length > 0;
  drawer.all.hidden = list.length === 0;
  drawer.confirm.hidden = true;
  drawer.error.hidden = true;
}

// 지운 대화를 보고 있었으면 그 모델의 새 대화로. 뒤 화면의 최근 대화 카드도 다시 그린다. ids가 null이면 전체
function afterDelete(ids) {
  if (chat.conv && (!ids || ids.includes(chat.conv.id))) {
    resetChat(chat.model, null);
    if (parseRoute(location.hash).screen === "chat") history.replaceState(null, "", chatHash(chat.model.id));
  }
  const { screen } = parseRoute(location.hash);
  if (RECENT_LIMIT[screen]) renderRecent($(`${screen}-recent`), RECENT_LIMIT[screen], drawerModels);
  renderDrawer();
}

function deleteOne(id, button) {
  if (!deleteConversation(storage(), id)) {  // 읽기·쓰기 실패나 다른 버전 데이터: 지우지 않았으니 목록은 그대로
    drawer.error.hidden = false;
    return;
  }
  const i = [...drawer.list.querySelectorAll("button")].indexOf(button);
  afterDelete([id]);
  const rest = [...drawer.list.querySelectorAll("button")];
  (rest[i] ?? rest[i - 1] ?? drawer.title).focus();  // 다음 카드의 삭제 버튼, 없으면 이전 것, 비면 제목
}

function closeConfirm() {
  drawer.confirm.hidden = true;
  drawer.all.hidden = false;
  drawer.all.focus();
}

// ← 주소는 지금 화면 기준(서랍을 열 때와, 열린 채 주소가 바뀔 때 다시 정한다)
function updateBack() {
  const back = parentHash(parseRoute(location.hash), drawerModels);
  if (!back && document.activeElement === drawer.back) drawer.title.focus();  // 숨기기 전에 옮긴다(body로 떨어지지 않게)
  drawer.back.hidden = !back;  // 가전 고르기에서는 ⌂와 같아서 숨긴다
  if (back) drawer.back.href = back;
}

ui.menu.addEventListener("click", async () => {
  drawerModels = await modelsReady;
  renderDrawer();
  updateBack();
  $("drawer-login-error").hidden = true;
  if (!drawer.box.open) drawer.box.showModal();
  drawer.title.focus();
  updateAccount();  // 공개 설정·Supabase는 서랍을 열 때 처음 부른다(첫 화면에서는 부르지 않음)
});
$("drawer-close").addEventListener("click", () => drawer.box.close());
drawer.box.addEventListener("click", (e) => {  // 대화 카드·새 대화는 주소로 이동
  if (!e.target.closest("a")) return;
  closedByLink = true;
  drawer.box.close();
});
// 링크로 닫으면 그 화면의 h1로(주소가 같으면 hashchange가 없어 여기서 옮긴다), 그 밖에는 ☰로(브라우저가 돌려주지 않아도)
drawer.box.addEventListener("close", () => {
  if (closedByLink) heading(parseRoute(location.hash).screen).focus({ preventScroll: true });
  else ui.menu.focus();
  closedByLink = false;
});
drawer.all.addEventListener("click", () => {
  drawer.confirmText.textContent = `대화 ${loadConversations(storage()).length}개를 모두 지울까요?`;
  drawer.all.hidden = true;
  drawer.confirm.hidden = false;
  drawer.cancel.focus();
});
drawer.cancel.addEventListener("click", closeConfirm);
$("delete-ok").addEventListener("click", () => {
  if (!deleteAllConversations(storage())) {
    closeConfirm();
    drawer.error.hidden = false;
    return;
  }
  afterDelete(null);
  drawer.title.focus();
});

// ── 2차 내 모델 요청(계획 Task 6): 로그인은 요청할 때만(로그인 벽 없음). 첫 화면에서는 Supabase를 부르지 않는다 ──
const RETURN_KEY = "pyeobom.returnTo";  // 구글로 떠나기 전 경로(#request/<가전>)만 둔다. 이메일은 두지 않는다
const req = {
  kind: $("request-kind"), form: $("request-form"), brand: $("request-brand"), model: $("request-model"),
  hint: $("request-hint"), error: $("request-error"), submit: $("request-submit"),
  exists: $("request-exists"), existsName: $("request-exists-name"), done: $("request-done"),
};
let requestAppliance = null;
let existingModel = null;

function prepareRequest(appliance) {  // 입력한 값은 그대로 두고 안내만 지운다(로그인하고 돌아와도 이어서 쓰게)
  requestAppliance = appliance;
  req.kind.textContent = APPLIANCES[appliance];
  req.error.hidden = req.exists.hidden = req.done.hidden = true;
}

// 모델명 찾는 법은 1.5차 모델 카드의 안내를 다시 쓴다. 모델이 없는 종류(건조기)는 세탁기 안내(둘 다 본체 라벨)
function showRequestHint(appliance, models) {
  const source = models.find((m) => m.appliance === appliance) ?? models.find((m) => m.appliance === "washer");
  req.hint.hidden = !source;
  if (source) req.hint.replaceChildren(el("strong", null, "모델명 찾는 법 "), source.model_name_hint);
}

// 안내 글자는 보일 때만 넣는다(숨은 같은 문장이 여러 곳에 남지 않게)
function showError(box, message) {
  box.textContent = message;
  box.hidden = false;
}
const showRequestError = (message) => showError(req.error, message);

async function requireLogin(hash) {
  const auth = await initAuth();
  if (!auth) showRequestError(UNAVAILABLE);
  else if (!(await auth.session())) openLogin({ reason: true, then: hash });
}

$("no-model").addEventListener("click", async () => {
  const appliance = parseRoute(location.hash).appliance;
  $("no-model-error").hidden = true;
  const auth = await initAuth();
  if (!auth) {
    showError($("no-model-error"), UNAVAILABLE);
    return;
  }
  const target = `#request/${appliance}`;
  if (await auth.session()) location.hash = target;
  else openLogin({ reason: true, then: target });
});

req.form.addEventListener("submit", async (e) => {
  e.preventDefault();
  req.error.hidden = req.exists.hidden = req.done.hidden = true;
  const input = { appliance: requestAppliance, brand: req.brand.value, modelText: req.model.value };
  const invalid = validateRequest(input);
  if (invalid) return showRequestError(invalid);
  existingModel = findExistingModel(await modelsReady, requestAppliance, input.modelText);
  if (existingModel) {  // 이미 있는 모델은 요청을 넣지 않고 바로 질문하게 한다
    req.existsName.textContent = existingModel.name;
    req.exists.hidden = false;
    return;
  }
  const auth = await initAuth();
  if (!auth) return showRequestError(UNAVAILABLE);
  req.submit.disabled = true;
  let result;
  try {
    result = await auth.client.from("model_requests").insert(requestRow(input));
  } catch {
    result = { status: 0, error: {} };
  } finally {
    req.submit.disabled = false;
  }
  if (!result.error) {
    req.form.reset();
    req.done.hidden = false;
    return;
  }
  const message = requestErrorMessage(result);
  if (message === LOGIN_REQUIRED) openLogin({ reason: true, then: location.hash });
  else showRequestError(message);
});
$("request-ask").addEventListener("click", () => { location.hash = chatHash(existingModel.id); });

// ── 로그인 시트(덧붙임 D-3·D-4): ① 이메일 → 코드 보내기 또는 구글 ② 코드 입력 ──
const WRONG_CODE = "코드가 맞지 않아요. 다시 확인해 주세요";
const RESEND_WAIT = "잠시 뒤에 다시 보낼 수 있어요";
const SEND_FAILED = "메일을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요";
const login = {
  box: $("login-sheet"), reason: $("login-reason"), emailForm: $("login-email-form"), email: $("login-email"),
  emailError: $("login-email-error"), codeForm: $("login-code-form"), code: $("login-code"), codeError: $("login-code-error"),
  sentEmail: $("login-sent-email"), resent: $("login-resent"),
};
let loginThen = null;  // 로그인한 뒤 갈 주소(요청 화면). 서랍에서 열면 없음
let sentTo = "";

function loginStep(n) {
  login.emailForm.hidden = n !== 1;
  login.codeForm.hidden = n !== 2;
  login.emailError.hidden = login.codeError.hidden = login.resent.hidden = true;
  (n === 1 ? login.email : login.code).focus();
}

const loginError = showError;

async function whileBusy(box, work) {
  const buttons = [...box.querySelectorAll("button")];
  const active = document.activeElement;  // 잠긴 버튼에서 포커스가 body로 떨어지므로 끝나면 돌려준다
  buttons.forEach((b) => { b.disabled = true; });
  try {
    return await work();
  } finally {
    buttons.forEach((b) => { b.disabled = false; });
    if (buttons.includes(active)) active.focus();
  }
}

function openLogin({ reason = false, then = null } = {}) {
  loginThen = then;
  login.reason.hidden = !reason;
  if (!login.box.open) login.box.showModal();
  loginStep(1);
}

const sendError = (error) => (error.status === 429 ? RESEND_WAIT : SEND_FAILED);  // 같은 사람 60초에 1번(429)

login.emailForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = login.email.value.trim();
  if (!email || !login.email.checkValidity()) return loginError(login.emailError, "이메일 주소를 확인해 주세요");
  const auth = await initAuth();
  if (!auth) return loginError(login.emailError, UNAVAILABLE);
  const error = await whileBusy(login.emailForm, () => auth.sendCode(email));
  if (error) return loginError(login.emailError, sendError(error));
  sentTo = email;
  login.sentEmail.textContent = email;
  login.code.value = "";
  loginStep(2);
});

login.codeForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  login.resent.hidden = true;
  const code = login.code.value.replace(/\s/g, "");
  if (!isOtpCode(code)) return loginError(login.codeError, "숫자 6~10자리 코드를 넣어 주세요");
  const auth = await initAuth();
  if (!auth) return loginError(login.codeError, UNAVAILABLE);
  const error = await whileBusy(login.codeForm, () => auth.verifyCode(sentTo, code));
  if (error) return loginError(login.codeError, error.status && error.status < 500 ? WRONG_CODE : UNAVAILABLE);
  login.box.close();
  updateAccount();
  if (!loginThen) return;
  if (location.hash === loginThen) render(true);
  else location.hash = loginThen;
});

$("login-resend").addEventListener("click", async () => {
  login.codeError.hidden = login.resent.hidden = true;
  const auth = await initAuth();
  const error = auth ? await whileBusy(login.codeForm, () => auth.sendCode(sentTo)) : { status: 0 };
  if (error) loginError(login.codeError, sendError(error));
  else login.resent.hidden = false;
});
$("login-edit").addEventListener("click", () => loginStep(1));
$("login-close").addEventListener("click", () => login.box.close());

$("login-google").addEventListener("click", async () => {
  const auth = await initAuth();
  if (!auth) return loginError(login.emailError, UNAVAILABLE);
  try { sessionStorage.setItem(RETURN_KEY, loginThen ?? location.hash); } catch { /* 저장 못 하면 돌아와서 첫 화면 */ }
  // 돌아올 주소는 # 없는 사이트 주소(PKCE의 ?code=와 우리 # 경로가 섞이지 않게)
  const { error } = await auth.google(`${location.origin}/`);
  if (error) loginError(login.emailError, UNAVAILABLE);
});

// 서랍의 로그인·로그아웃(덧붙임 D-2): 로그인하면 같은 자리에 로그아웃
async function updateAccount() {
  const auth = await initAuth();
  const session = auth ? await auth.session() : null;
  $("drawer-login").hidden = Boolean(session);
  $("drawer-logout").hidden = !session;
}
$("drawer-login").addEventListener("click", async () => {
  $("drawer-login-error").hidden = true;
  if (!(await initAuth())) {
    showError($("drawer-login-error"), UNAVAILABLE);
    return;
  }
  drawer.box.close();
  openLogin();
});
$("drawer-logout").addEventListener("click", async () => {
  const auth = await initAuth();
  await auth?.signOut();
  await updateAccount();
  $("drawer-login").focus();
});

// 구글에서 돌아오면(?code=) 세션으로 바꾼 뒤 떠나기 전 경로로. 경로는 우리 주소 형식일 때만 쓴다
async function finishGoogleLogin() {
  let back = null;
  try {
    back = sessionStorage.getItem(RETURN_KEY);
    sessionStorage.removeItem(RETURN_KEY);
  } catch { /* 저장소를 못 쓰면 첫 화면 */ }
  const auth = await initAuth();
  const session = auth ? await auth.session() : null;  // detectSessionInUrl이 code를 세션으로 바꾼 뒤에 돌아온다
  history.replaceState(null, "", location.pathname);  // 주소의 code는 지운다
  if (session && back && parseRoute(back).screen !== "landing") location.hash = back;
}

// 처음 열면 # 부분과 상관없이 랜딩(계획 기본값 3). 주소의 #도 지워 뒤로 가기가 랜딩으로 오게 한다
history.replaceState(null, "", location.pathname + location.search);
window.addEventListener("hashchange", () => {
  if (drawer.box.open) updateBack();  // 서랍이 열린 채 브라우저 뒤로·앞으로
  render(true);
});
render(false);
if (new URLSearchParams(location.search).has("code")) finishGoogleLogin();
