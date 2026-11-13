import test from "node:test";
import assert from "node:assert/strict";
import { parentHash } from "../../../public/js/nav.js";

const models = [{ id: "washer-lg-fx25", appliance: "washer" }, { id: "aircon-lg-sq06fa1wds", appliance: "aircon" }];
test("채팅 → 그 가전의 모델 고르기", () =>
  assert.equal(parentHash({ screen: "chat", modelId: "aircon-lg-sq06fa1wds", conversationId: "c1" }, models), "#model/aircon"));
test("모델 고르기 → 가전 고르기", () =>
  assert.equal(parentHash({ screen: "model", appliance: "washer" }, models), "#category"));
test("가전 고르기·첫 화면은 없음", () => {
  assert.equal(parentHash({ screen: "category" }, models), null);
  assert.equal(parentHash({ screen: "landing" }, models), null);
});
test("모르는 모델·빈 목록이면 가전 고르기", () => {
  assert.equal(parentHash({ screen: "chat", modelId: "x" }, models), "#category");
  assert.equal(parentHash({ screen: "chat", modelId: "washer-lg-fx25" }, []), "#category");
});
