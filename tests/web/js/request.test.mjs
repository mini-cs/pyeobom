import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  normalizeModelKey, findExistingModel, validateRequest, requestErrorMessage, requestRow, LOGIN_REQUIRED,
  hasSavedLogin, sortRequests, summarizeRequests, requestView,
} from "../../../public/js/request.js";
import { isOtpCode } from "../../../public/js/auth.js";

// DB 생성 열(supabase/schema.sql model_key)과 같은 사례 파일(tests/requests/test_rls_live.py도 이 파일을 쓴다)
const CASES = JSON.parse(readFileSync(new URL("../../fixtures/model_key_cases.json", import.meta.url), "utf-8"));

test("normalizeModelKey: 사례 파일 전부 DB 정규화 값과 같다", () => {
  for (const c of CASES) assert.equal(normalizeModelKey(c.input), c.key, c.case);
});

// 가짜 모델 목록(/api/models와 같은 모양). 코드의 *는 "아무 글자나"(data/models.json의 FX25*N*처럼 가운데에도 온다)
const MODELS = [
  { id: "washer-fake-a", appliance: "washer", model_codes: ["WD90H25AH*", "WD90H25BH*"] },
  { id: "washer-fake-b", appliance: "washer", model_codes: ["FX25*N*"] },
  { id: "aircon-fake-c", appliance: "aircon", model_codes: ["SQ06FA1WDS"] },
];

test("findExistingModel: 끝 *는 그 앞부분으로 시작하면 같은 모델", () =>
  assert.equal(findExistingModel(MODELS, "washer", "WD90H25AH-1234")?.id, "washer-fake-a"));
test("findExistingModel: 소문자·기호를 빼고 비교", () =>
  assert.equal(findExistingModel(MODELS, "aircon", "sq06fa1-wds")?.id, "aircon-fake-c"));
test("findExistingModel: 가운데 *도 아무 글자나", () =>
  assert.equal(findExistingModel(MODELS, "washer", "FX25ABCN1")?.id, "washer-fake-b"));
test("findExistingModel: 다른 가전 종류의 모델은 찾지 않는다", () => {
  assert.equal(findExistingModel(MODELS, "dryer", "WD90H25AH-1234"), null);
  assert.equal(findExistingModel(MODELS, "aircon", "WD90H25AH-1234"), null);
});
test("findExistingModel: *가 없는 코드는 앞부분만 같아서는 아니다", () => {
  assert.equal(findExistingModel(MODELS, "aircon", "SQ06FA1"), null);
  assert.equal(findExistingModel(MODELS, "aircon", "SQ06FA1WDS2"), null);
});

const OK = { appliance: "dryer", brand: "가짜브랜드", modelText: "DV90-FAKE1" };
test("validateRequest: 맞는 요청은 null", () => {
  assert.equal(validateRequest(OK), null);
  assert.equal(validateRequest({ ...OK, modelText: "A".repeat(40) }), null);
  assert.equal(validateRequest({ ...OK, brand: "가".repeat(20) }), null);
});
test("validateRequest: 모델명 빈 입력·공백만", () => {
  assert.equal(validateRequest({ ...OK, modelText: "" }), "모델명을 입력해 주세요");
  assert.equal(validateRequest({ ...OK, modelText: "   " }), "모델명을 입력해 주세요");
});
test("validateRequest: 모델명 1자·41자(앞뒤 공백은 빼고 셈)", () => {
  assert.equal(validateRequest({ ...OK, modelText: " A " }), "모델명은 2~40자로 입력해 주세요");
  assert.equal(validateRequest({ ...OK, modelText: "A".repeat(41) }), "모델명은 2~40자로 입력해 주세요");
});
test("validateRequest: 영문·숫자가 없는 모델명(기호만·한글만)", () => {
  assert.equal(validateRequest({ ...OK, modelText: "-*/." }), "모델명에 영문이나 숫자를 넣어 주세요");
  assert.equal(validateRequest({ ...OK, modelText: "그랑데" }), "모델명에 영문이나 숫자를 넣어 주세요");
});
test("validateRequest: 브랜드 빈 입력·21자", () => {
  assert.equal(validateRequest({ ...OK, brand: "  " }), "브랜드를 입력해 주세요");
  assert.equal(validateRequest({ ...OK, brand: "가".repeat(21) }), "브랜드는 20자 이내로 입력해 주세요");
});
test("validateRequest: 세탁기·건조기·에어컨 밖의 가전 종류", () =>
  assert.equal(validateRequest({ ...OK, appliance: "fridge" }), "가전 종류를 골라 주세요"));

test("requestRow: 넣기는 세 열만(db.md 권한), 앞뒤 공백은 뺀다", () =>
  assert.deepEqual(requestRow({ appliance: "dryer", brand: " 가짜브랜드 ", modelText: " DV90-FAKE1 " }),
    { category: "dryer", brand: "가짜브랜드", model_text: "DV90-FAKE1" }));

// 갈래(2026-11-25 사용자 결정): 하루 제한은 트리거라 P0001(HTTP 400)로 온다(계획의 42501에서 바뀜)
test("requestErrorMessage: 같은 모델명 다시 요청(23505)", () =>
  assert.equal(requestErrorMessage({ status: 409, error: { code: "23505" } }), "이미 요청하셨어요"));
test("requestErrorMessage: 24시간 5개(트리거 P0001)", () =>
  assert.equal(requestErrorMessage({ status: 400, error: { code: "P0001" } }),
    "오늘은 요청을 더 받을 수 없어요. 내일 다시 요청해 주세요"));
test("requestErrorMessage: 로그인 끊김(401)이면 로그인 시트", () =>
  assert.equal(requestErrorMessage({ status: 401, error: { code: "PGRST303" } }), LOGIN_REQUIRED));
test("requestErrorMessage: 그 밖(권한 42501·연결 실패)은 잠시 쓸 수 없어요", () => {
  assert.equal(requestErrorMessage({ status: 403, error: { code: "42501" } }), "잠시 쓸 수 없어요");
  assert.equal(requestErrorMessage({ status: 0, error: { message: "Failed to fetch" } }), "잠시 쓸 수 없어요");
});

test("isOtpCode: 숫자 6~10자리만(길이 고정 안 함, 덧붙임 A-2)", () => {
  for (const ok of ["123456", "12345678", "1234567890"]) assert.equal(isOtpCode(ok), true, ok);
  for (const bad of ["12345", "12345678901", "12a456", "", "123 456"]) assert.equal(isOtpCode(bad), false, bad);
});

test("hasSavedLogin: Supabase 로그인 기록 키가 있을 때만 true(값은 보지 않음)", () => {
  const store = (keys) => ({ length: keys.length, key: (i) => keys[i] });
  assert.equal(hasSavedLogin(store(["pyeobom.conversations", "sb-supabase-auth-token"])), true);
  assert.equal(hasSavedLogin(store(["pyeobom.conversations", "sb-auth-token", "sb-x-auth-token-code-verifier"])), false);
  assert.equal(hasSavedLogin({ get length() { throw new Error("막힘"); } }), false);
});

test("sortRequests·summarizeRequests: 최근에 바뀐 순, 상태 개수는 정한 순서·0은 뺌", () => {
  const rows = [
    { id: 1, status: "대기", updated_at: "2026-11-26T03:00:00Z" },
    null,
    { id: 2, status: "추가됨", updated_at: "2026-11-27T03:00:00Z" },
    { id: 3, status: "확인 중", updated_at: "2026-11-27T01:00:00Z" },
  ];
  assert.deepEqual(sortRequests(rows).map((r) => r.id), [2, 3, 1]);
  assert.deepEqual(summarizeRequests(rows), { total: 3, parts: [
    { status: "추가됨", count: 1 }, { status: "확인 중", count: 1 }, { status: "대기", count: 1 }] });
});

test("requestView: 추가됨은 배포된 모델일 때만 누를 수 있고, 추가 어려움은 사유", () => {
  const deployed = new Set(["washer-lg-fx21wnc"]);
  const base = { brand: " LG ", model_text: "FX21WNC ", category: "washer", updated_at: "2026-11-27T03:00:00Z" };
  assert.deepEqual(requestView({ ...base, status: "추가됨", model_id: "washer-lg-fx21wnc" }, deployed), {
    title: "LG FX21WNC", category: "washer", status: "추가됨", updatedAt: "2026-11-27T03:00:00Z",
    extra: "눌러서 바로 질문하기", href: "#chat/washer-lg-fx21wnc" });
  const hidden = requestView({ ...base, status: "추가됨", model_id: "dryer-fake-not-deployed" }, deployed);
  assert.equal(hidden.href, null); assert.equal(hidden.extra, null);
  assert.equal(requestView({ ...base, status: "추가 어려움", reason: " 글자가 없는 설명서(테스트) " }, deployed).extra,
    "사유: 글자가 없는 설명서(테스트)");
  assert.equal(requestView({ ...base, status: "대기" }, deployed).extra, null);
});
