// 펴봄 화면: 모델 고르기 → 질문 → 답변 카드(근거) / 찾지 못함 / 오류. API 글자는 textContent로만 넣는다(XSS 방지).
const MAX_LEN = 500;
const STORE_KEY = "pyeobom.model";
const EXAMPLES = {
  washer: ["통세척은 어떻게 해요?", "에러 코드가 떴어요"],
  aircon: ["필터 청소는 어떻게 해요?", "찬바람이 안 나와요"],
};
const NETWORK_ERROR = "일시적인 문제가 생겼어요. 잠시 후 다시 시도해 주세요";

const $ = (id) => document.getElementById(id);
const ui = {
  modelName: $("model-name"), modelChange: $("model-change"), picker: $("model-picker"), list: $("model-list"),
  form: $("ask-form"), question: $("question"), counter: $("counter"), send: $("send"),
  formError: $("form-error"), pii: $("pii-note"), examples: $("examples"), result: $("result"), intro: $("intro"),
};

let models = [];
let current = null;
let busy = false;
let sent = false;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function link(text, href) {
  const a = el("a", "doc-link", text);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

function searchTerm(model) {
  const m = model.display_name.match(/\(([^)]+)\)/);  // "LG 벽걸이 에어컨 (SQ06FA1WDS)" → "SQ06FA1WDS"
  return m ? m[1] : model.display_name;
}

function remember(id) {
  try { localStorage.setItem(STORE_KEY, id); } catch { /* 저장 못 해도 동작은 같다 */ }
}

function recall() {
  try { return localStorage.getItem(STORE_KEY); } catch { return null; }
}

// ── 소개 영역 접기(기획서 4.2) ──
function collapse(on) {
  document.body.classList.toggle("is-collapsed", on);
  ui.intro.setAttribute("aria-hidden", String(on));
}

// ── 모델 ──
function renderModels() {
  ui.list.replaceChildren(...models.map((m) => {
    const li = el("li");
    const b = el("button", "model-option");
    b.type = "button";
    b.setAttribute("aria-pressed", String(current && m.id === current.id));
    b.append(el("span", null, m.display_name), el("span", "model-option-hint", m.model_name_hint));
    b.addEventListener("click", () => selectModel(m, true));
    li.append(b);
    return li;
  }));
}

function renderExamples() {
  const items = EXAMPLES[current?.appliance] || [];
  ui.examples.replaceChildren(...items.map((q) => {
    const b = el("button", "example", q);
    b.type = "button";
    b.addEventListener("mousedown", (e) => e.preventDefault());  // 검색창 포커스를 잃지 않게
    b.addEventListener("click", () => {
      ui.question.value = q;
      updateCounter();
      collapse(true);
      ask();
    });
    return b;
  }));
}

function selectModel(model, fromPicker) {
  current = model;
  ui.modelName.textContent = model.display_name;
  remember(model.id);
  renderModels();
  renderExamples();
  if (fromPicker) {
    togglePicker(false);
    ui.result.replaceChildren(el("p", "empty", `${model.display_name} 기준으로 답해 드려요.`));
  }
}

function togglePicker(open) {
  ui.picker.hidden = !open;
  ui.modelChange.setAttribute("aria-expanded", String(open));
}

async function loadModels() {
  try {
    const res = await fetch("/api/models");
    if (!res.ok) throw new Error(String(res.status));
    models = await res.json();
    const saved = models.find((m) => m.id === recall());
    selectModel(saved || models[0], false);
  } catch {
    ui.modelName.textContent = "모델 목록을 불러오지 못했어요. 새로고침해 주세요";
  }
}

// ── 질문 ──
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
    const b = el("button", "retry", "다시 시도");
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
  sent = true;
  collapse(true);
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

// ── 이벤트 ──
ui.modelChange.addEventListener("click", () => togglePicker(ui.picker.hidden));
ui.question.addEventListener("input", updateCounter);
ui.question.addEventListener("focus", () => collapse(true));
ui.question.addEventListener("blur", () => {
  if (!ui.question.value.trim() && !sent) collapse(false);
});
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

updateCounter();
loadModels();
