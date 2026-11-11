import test from "node:test";
import assert from "node:assert/strict";
import { STORE_KEY, LIMITS, loadConversations, saveConversation, deleteConversation, deleteAllConversations, toStoredTurn, makeTitle } from "../../../public/js/store.js";

// 가짜 저장소: getItem/setItem만 가진 작은 객체
function fakeStorage(initial) {
  const data = new Map(initial === undefined ? [] : [[STORE_KEY, initial]]);
  return { getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => void data.set(k, v) };
}
const conv = (id, n = 0, turns = []) => ({ id, model_id: "m", title: id, created_at: "2026-01-01T00:00:00.000Z", updated_at: new Date(Date.UTC(2026, 0, 1, 0, 0, n)).toISOString(), turns });
const turn = (i) => ({ question_masked: `q${i}`, rewritten_question: null, answer: `a${i}`, found: true, citations: [], kind: "answer" });

test("load: 빈 저장소·깨진 JSON·다른 버전·예외는 []", () => {
  assert.deepEqual(loadConversations(fakeStorage()), []);
  assert.deepEqual(loadConversations(fakeStorage("{")), []);
  assert.deepEqual(loadConversations(fakeStorage(JSON.stringify({ version: 99, conversations: [conv("a")] }))), []);
  assert.deepEqual(loadConversations(fakeStorage(JSON.stringify({ version: 1, conversations: "x" }))), []);
  assert.deepEqual(loadConversations({ getItem() { throw new Error("blocked"); } }), []);
});

test("save: setItem 예외는 false, 밖으로 나오지 않음", () => {
  const s = { getItem: () => null, setItem() { throw new Error("quota"); } };
  assert.equal(saveConversation(s, conv("a")), false);
});

test("save/load: 저장 후 updated_at 최신순", () => {
  const s = fakeStorage();
  assert.equal(saveConversation(s, conv("old", 1)), true);
  assert.equal(saveConversation(s, conv("new", 2)), true);
  assert.deepEqual(loadConversations(s).map((c) => c.id), ["new", "old"]);
  assert.equal(JSON.parse(s.getItem(STORE_KEY)).version, 1);
});

test("한도: 21번째 대화는 가장 오래된 것을 뺀다", () => {
  const s = fakeStorage();
  for (let i = 0; i < 21; i++) saveConversation(s, conv(`c${i}`, i));
  const ids = loadConversations(s).map((c) => c.id);
  assert.equal(ids.length, LIMITS.conversations);
  assert.ok(!ids.includes("c0") && ids.includes("c20"));
});

test("한도: 31번째 턴은 가장 오래된 턴을 뺀다", () => {
  const s = fakeStorage();
  saveConversation(s, conv("a", 1, Array.from({ length: 31 }, (_, i) => turn(i))));
  const turns = loadConversations(s)[0].turns;
  assert.equal(turns.length, LIMITS.turns);
  assert.equal(turns[0].question_masked, "q1");
  assert.equal(turns.at(-1).question_masked, "q30");
});

test("탭 두 개: 서로 모르는 대화 A·B가 모두 남는다", () => {
  const s = fakeStorage();
  saveConversation(s, conv("A", 1));
  saveConversation(s, conv("B", 2)); // 이 탭은 A를 모르는 상태
  assert.deepEqual(loadConversations(s).map((c) => c.id).sort(), ["A", "B"]);
});

test("save: 같은 id는 바꾼다", () => {
  const s = fakeStorage();
  saveConversation(s, conv("A", 1));
  saveConversation(s, conv("A", 2, [turn(1)]));
  const all = loadConversations(s);
  assert.equal(all.length, 1);
  assert.equal(all[0].turns.length, 1);
});

test("delete: 하나·전체, 없는 id도 true, 예외는 false", () => {
  const s = fakeStorage();
  saveConversation(s, conv("A", 1));
  saveConversation(s, conv("B", 2));
  assert.equal(deleteConversation(s, "A"), true);
  assert.equal(deleteConversation(s, "none"), true);
  assert.deepEqual(loadConversations(s).map((c) => c.id), ["B"]);
  assert.equal(deleteAllConversations(s), true);
  assert.deepEqual(loadConversations(s), []);
  const bad = { getItem: () => null, setItem() { throw new Error("x"); } };
  assert.equal(deleteConversation(bad, "A"), false);
  assert.equal(deleteAllConversations(bad), false);
});

test("toStoredTurn: 오류 응답은 null", () => {
  assert.equal(toStoredTurn({ error_code: "RATE_LIMITED", message: "잠시 후" }), null);
});

test("toStoredTurn: 키는 정확히 6개, question 없음, kind 정하기", () => {
  const base = { found: true, answer: "답", citations: [{ page: 1 }], official_url: "u", latency_ms: 5, pii_masked: false, question_masked: "질문", rewritten_question: null, reason: null };
  const t = toStoredTurn({ ...base, question: "원래 질문(010-1234-5678)" });
  assert.deepEqual(Object.keys(t).sort(), ["answer", "citations", "found", "kind", "question_masked", "rewritten_question"]);
  assert.ok(!("question" in t));
  assert.equal(t.kind, "answer");
  assert.equal(toStoredTurn({ ...base, found: false }).kind, "not_found");
  assert.equal(toStoredTurn({ ...base, found: false, reason: "other_brand" }).kind, "other_brand");
});

test("makeTitle: 앞 30자(코드 포인트 단위)", () => {
  assert.equal(makeTitle("가".repeat(40)), "가".repeat(30));
  assert.equal(makeTitle("짧은 질문"), "짧은 질문");
  assert.equal(Array.from(makeTitle("😀".repeat(40))).length, 30);
});

// 감시용 저장소: setItem 호출 횟수를 센다
function spyStorage(raw) {
  const s = { raw, sets: 0, getItem: () => s.raw ?? null, setItem(k, v) { s.sets++; s.raw = v; } };
  return s;
}

test("load: 깨진 항목([null], turns가 배열 아님)은 버리고 올바른 것만 남긴다", () => {
  const good = conv("ok", 1);
  const raw = JSON.stringify({ version: 1, conversations: [null, good, { id: "x", updated_at: "2026-01-01T00:00:00.000Z", turns: "no" }, { id: 3, updated_at: "t", turns: [] }] });
  const s = spyStorage(raw);
  assert.deepEqual(loadConversations(s).map((c) => c.id), ["ok"]);
  assert.equal(saveConversation(s, conv("new", 2)), true);
  assert.deepEqual(loadConversations(s).map((c) => c.id), ["new", "ok"]);
});

test("읽기 실패(getItem 예외): 저장·삭제는 쓰지 않고 false", () => {
  const s = { sets: 0, getItem() { throw new Error("blocked"); }, setItem() { s.sets++; } };
  assert.equal(saveConversation(s, conv("a")), false);
  assert.equal(deleteConversation(s, "a"), false);
  assert.equal(deleteAllConversations(s), false);
  assert.equal(s.sets, 0);
});

test("다른 버전이 저장돼 있으면 덮어쓰지 않고 false", () => {
  const raw = JSON.stringify({ version: 2, conversations: [conv("future", 1)] });
  const s = spyStorage(raw);
  assert.equal(saveConversation(s, conv("a")), false);
  assert.equal(deleteConversation(s, "a"), false);
  assert.equal(deleteAllConversations(s), false);
  assert.equal(s.sets, 0);
  assert.equal(s.raw, raw);
});

test("읽을 수 없는 JSON(\"{\")은 덮어써서 version 1로 쓴다", () => {
  const s = spyStorage("{");
  assert.equal(saveConversation(s, conv("a", 1)), true);
  assert.equal(JSON.parse(s.raw).version, 1);
});
