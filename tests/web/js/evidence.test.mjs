import test from "node:test";
import assert from "node:assert/strict";
import { docLinks, evidenceLabel, groupCitations, offerText, warnings } from "../../../public/js/evidence.js";

const URL_M = "https://example.com/manual";
const URL_G = "https://example.com/guide";
const m = (page, quote) => ({ doc_type: "manual", title: "가짜 설명서", page, url: URL_M, quote });
const g = (title, quote, url = URL_G) => ({ doc_type: "guide", title, page: null, url, quote, warning: "공용 경고" });

test("evidenceLabel: 쪽은 중복 없이 오름차순, 가이드는 문서 수", () => {
  assert.equal(evidenceLabel([m(38, "a")]), "근거 보기 · 사용설명서 38쪽");
  assert.equal(evidenceLabel([m(72, "a"), m(38, "b"), m(50, "c"), m(38, "d")]), "근거 보기 · 사용설명서 38·50·72쪽");
  assert.equal(evidenceLabel([m(71, "a"), g("가이드 A", "x"), g("가이드 A", "y")]), "근거 보기 · 사용설명서 71쪽 · 공식 해결 가이드 1개");
  assert.equal(evidenceLabel([g("가이드 A", "x"), g("가이드 B", "y", "https://example.com/b")]), "근거 보기 · 공식 해결 가이드 2개");
});

test("groupCitations: 설명서는 쪽별, 가이드는 문서별, 처음 나온 순서", () => {
  const groups = groupCitations([m(38, "a"), g("가이드 A", "x"), m(12, "b"), m(38, "c"), g("가이드 A", "y")]);
  assert.deepEqual(groups.map((x) => [x.doc_type, x.page, x.title, x.quotes]), [
    ["manual", 38, "가짜 설명서", ["a", "c"]],
    ["guide", null, "가이드 A", ["x", "y"]],
    ["manual", 12, "가짜 설명서", ["b"]],
  ]);
});

test("객체가 아닌 근거는 버린다", () => {
  assert.deepEqual(groupCitations([null, "가짜", 3, m(5, "a")]).map((x) => x.page), [5]);
  assert.deepEqual(groupCitations(undefined), []);
  assert.equal(evidenceLabel([null]), "근거 보기");
});

test("warnings: 같은 문구는 한 번만", () => {
  assert.deepEqual(warnings([g("가이드 A", "x"), g("가이드 B", "y"), m(1, "a")]), ["공용 경고"]);
  assert.deepEqual(warnings([m(1, "a")]), []);
});

test("offerText: 설명서·문서 종류에 따라", () => {
  assert.equal(offerText([m(1, "a")]), "공식 설명서를 드릴까요?");
  assert.equal(offerText([g("가이드 A", "x")]), "공식 문서를 드릴까요?");
  assert.equal(offerText([m(1, "a"), g("가이드 A", "x")]), "공식 설명서·문서를 드릴까요?");
});

test("docLinks: URL 중복 없이, 설명서는 검색어, 가이드는 이름", () => {
  const links = docLinks([m(38, "a"), m(50, "b"), g("가이드 A", "x"), g("가이드 A", "y")], ["WD90H25AH*", "WD90H25BH*"]);
  assert.deepEqual(links, [
    { url: URL_M, text: "공식 설명서 받기 (검색어: WD90H25AH*·WD90H25BH*)" },
    { url: URL_G, text: "공식 문서 열기: 가이드 A" },
  ]);
  assert.deepEqual(docLinks([{ ...m(1, "a"), url: "" }], ["X"]), []);
});
