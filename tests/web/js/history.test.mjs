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

test("buildHistory: 질문은 서버 한도(500자) 안으로 잘라 보낸다(저장된 턴은 그대로)", () => {
  const long = "가린질문".repeat(160);  // 640자: 가린 뒤 길어진 질문(2026-11-11 최종 검토 M1)
  const turns = [{ question_masked: long, answer: "a" }, { question_masked: "짧은 질문", answer: "b" }];
  const h = buildHistory(turns);
  assert.equal(h[0].question, long.slice(0, 500));
  assert.equal(h[1].question, "짧은 질문");
  assert.equal(turns[0].question_masked, long);
  const emoji = "😀".repeat(600);  // 서버는 글자(코드 포인트) 수로 잰다. 반쪽 글자를 남기지 않는다
  assert.equal([...buildHistory([{ question_masked: emoji, answer: "a" }])[0].question].length, 500);
  assert.equal(buildHistory([{ question_masked: emoji, answer: "a" }])[0].question, "😀".repeat(500));
});
