// 펴봄 화면 전환: ① 랜딩 → ② 카테고리 → ③ 모델 → ④ 채팅(# 주소, 브라우저 뒤로 가기). API 글자는 textContent로만 넣는다(XSS 방지).
import { loadConversations } from "./js/store.js";

const MAX_LEN = 500;
// 모델별 예시 질문: 실제 /api/ask로 근거가 나오는 것을 확인한 문장, 평가 질문 30개와 겹치지 않게(2026-10-29)
const EXAMPLES = {
  "washer-samsung-wd90h25": ["이불 코스는 어떻게 해요?", "물이 안 빠지고 5C가 떠요"],
  "washer-lg-fx25": ["통세척은 어떻게 해요?", "UE 에러가 떴어요"],
  "aircon-lg-sq06fa1wds": ["필터 청소는 어떻게 해요?", "꺼짐 예약은 어떻게 해요?"],
};
const NETWORK_ERROR = "일시적인 문제가 생겼어요. 잠시 후 다시 시도해 주세요";
const MODELS_ERROR = "모델 목록을 불러오지 못했어요. 새로고침해 주세요";
const APPLIANCES = { washer: "세탁기", aircon: "에어컨" };
const RECENT_LIMIT = { landing: 1, category: 3 };  // 설계 2절 ①·②, 계획 기본값 5

const $ = (id) => document.getElementById(id);
const ui = {
  topbar: $("topbar"), tiles: $("tiles"), dots: $("tile-dots"),
  modelTitle: $("model-title"), modelCards: $("model-cards"), chatTitle: $("chat-title"),
  form: $("ask-form"), question: $("question"), counter: $("counter"), send: $("send"),
  formError: $("form-error"), pii: $("pii-note"), examples: $("examples"), result: $("result"),
};

let current = null;
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

function searchTerm(model) {
  return model.model_codes.join("·");  // 설명서 내려받기 페이지에서 찾을 모델 코드(예: "FX25*N*·FX24*N*·FX23*N*")
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
  if (focus) {
    window.scrollTo(0, 0);
    document.querySelector(`[data-screen="${name}"] h1`).focus();
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
    if (model) openChat(model);
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

ui.tiles.addEventListener("keydown", (e) => {
  const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
  if (!step) return;
  const tiles = [...ui.tiles.querySelectorAll(".tile")];
  const next = tiles[tiles.indexOf(document.activeElement) + step];
  if (next) {
    e.preventDefault();
    next.focus();
  }
});
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

// ── ④ 채팅(임시: 1차 질문·답 흐름. Task 5에서 대화형으로 바꾼다) ──
function openChat(model) {
  ui.chatTitle.textContent = model.name;
  if (current?.id === model.id) return;
  current = model;
  ui.question.value = "";
  updateCounter();
  showFormError("");
  ui.pii.hidden = true;
  ui.result.replaceChildren(el("p", "empty", `${model.name} 기준으로 답해 드려요.`));
  renderExamples();
}

function renderExamples() {
  const items = EXAMPLES[current?.id] || [];
  ui.examples.replaceChildren(...items.map((q) => {
    const b = el("button", "example", q);
    b.type = "button";
    b.addEventListener("click", () => {
      ui.question.value = q;
      updateCounter();
      ask();
    });
    return b;
  }));
}

function updateCounter() {
  const left = MAX_LEN - ui.question.value.length;
  ui.counter.textContent = `${left}자 남음`;
  ui.counter.classList.toggle("is-low", left <= 50);
}

function showFormError(message) {
  ui.formError.textContent = message;
  ui.formError.hidden = !message;
}

function setBusy(on) {
  busy = on;
  ui.send.disabled = on;
  ui.send.textContent = on ? "찾는 중…" : "물어보기";
}

function renderLoading() {
  const box = el("div", "loading");
  box.append(el("span", null, "설명서를 펴 보는 중…"), el("div", "progress"));
  ui.result.replaceChildren(box);
}

function renderError(message, retry) {
  const card = el("div", "card is-error");
  card.setAttribute("role", "alert");
  card.append(el("p", null, message));
  if (retry) {
    const b = el("button", "pill", "다시 시도");
    b.type = "button";
    b.addEventListener("click", ask);
    card.append(b);
  }
  ui.result.replaceChildren(card);
}

function renderEvidence(c) {
  const box = el("div", "evidence");
  if (c.doc_type === "manual") {
    box.append(el("p", "evidence-label", `사용설명서 ${c.page}쪽`), el("p", "evidence-title", c.title));
  } else {
    box.append(el("p", "evidence-label", `공식 해결 가이드: ${c.title}`));
  }
  box.append(el("blockquote", null, c.quote));
  if (c.warning) box.append(el("p", "warning", c.warning));
  // 설명서는 다운로드 페이지라 검색어를 함께 알려 준다(계획 Task 11 메모)
  box.append(c.doc_type === "manual"
    ? link(`공식 설명서 받기 (검색어: ${searchTerm(current)})`, c.url)
    : link("공식 문서 열기", c.url));
  return box;
}

function renderAnswer(data, question) {
  const card = el("article", "card");
  card.append(el("h2", null, question), el("p", "answer", data.answer));
  if (data.found) {
    data.citations.forEach((c) => card.append(renderEvidence(c)));
  } else {
    card.append(link("공식 고객센터에서 찾아보기", data.official_url));
  }
  ui.result.replaceChildren(card);
}

async function ask() {
  if (busy || !current) return;
  const question = ui.question.value.trim();
  if (!question) return showFormError("질문을 입력해 주세요");
  if (question.length > MAX_LEN) return showFormError(`질문은 ${MAX_LEN}자 이내로 입력해 주세요`);
  showFormError("");
  ui.pii.hidden = true;  // 이전 질문의 안내가 남지 않게
  setBusy(true);
  renderLoading();
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: current.id, question }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error_code) {
      // 입력 오류는 고쳐서 다시 보내면 되고, 그 밖의 오류는 같은 질문으로 다시 시도한다
      const inputError = ["EMPTY_QUESTION", "QUESTION_TOO_LONG", "INVALID_MODEL"].includes(data.error_code);
      renderError(data.message || NETWORK_ERROR, !inputError);
      return;
    }
    ui.pii.hidden = !data.pii_masked;
    renderAnswer(data, question);
  } catch {
    renderError(NETWORK_ERROR, true);
  } finally {
    setBusy(false);
  }
}

ui.question.addEventListener("input", updateCounter);
ui.question.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {  // 한글 조합 중 Enter는 무시
    e.preventDefault();
    ask();
  }
});
ui.form.addEventListener("submit", (e) => {
  e.preventDefault();
  ask();
});

// 처음 열면 # 부분과 상관없이 랜딩(계획 기본값 3). 주소의 #도 지워 뒤로 가기가 랜딩으로 오게 한다
history.replaceState(null, "", location.pathname + location.search);
window.addEventListener("hashchange", () => render(true));
render(false);
