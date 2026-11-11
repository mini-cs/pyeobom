import test from "node:test";
import assert from "node:assert/strict";
import { buildHistory, shouldShowRewritten } from "../../../public/js/history.js";

test("buildHistory: 5턴이면 마지막 3턴, 키는 question·answer뿐", () => {
  const turns = Array.from({ length: 5 }, (_, i) => ({ question_masked: `q${i}`, rewritten_question: "r", answer: `a${i}`, found: true, citations: [{ page: 1 }], kind: "answer" }));
  const h = buildHistory(turns);
  assert.deepEqual(h, [2, 3, 4].map((i) => ({ question: `q${i}`, answer: `a${i}` })));
  for (const x of h) assert.deepEqual(Object.keys(x).sort(), ["answer", "question"]);
  assert.deepEqual(buildHistory([]), []);
});

test("shouldShowRewritten", () => {
  assert.equal(shouldShowRewritten("IE 에러", null), false);
  assert.equal(shouldShowRewritten("IE 에러", ""), false);
  assert.equal(shouldShowRewritten("  IE  에러 ", "IE 에러"), false);
  assert.equal(shouldShowRewritten("그거 뭐야", "세탁기 IE 에러는 뭐야"), true);
});
