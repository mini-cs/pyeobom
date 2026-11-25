// 2차 "내 모델 요청"(계획 Task 6): 모델명 정규화·이미 있는 모델 찾기·입력 확인·거절 문구. 화면(DOM)에는 닿지 않는다
export const APPLIANCE_CODES = ["washer", "dryer", "aircon"];
export const LOGIN_REQUIRED = "login";  // 로그인이 끊김: 문장 대신 로그인 시트를 연다
export const UNAVAILABLE = "잠시 쓸 수 없어요";

// DB 생성 열 model_key와 같은 규칙(supabase/schema.sql, 사례는 tests/fixtures/model_key_cases.json)
export function normalizeModelKey(text) {
  return String(text ?? "").replace(/[^0-9A-Za-z가-힣]/g, "").toUpperCase();
}

// 모델 코드의 *는 자리와 상관없이 "아무 글자나"(data/models.json의 FX25*N*처럼 가운데에도 온다)
function codeMatches(code, key) {
  const parts = String(code).split("*").map(normalizeModelKey);  // 정규화하면 영문·숫자·한글만 남아 정규식에 그대로 넣어도 된다
  return new RegExp(`^${parts.join(".*")}$`).test(key);
}

export function findExistingModel(models, appliance, text) {
  const key = normalizeModelKey(text);
  if (!key) return null;
  return models.find((m) => m.appliance === appliance && m.model_codes.some((c) => codeMatches(c, key))) ?? null;
}

// 글자 수는 DB(char_length)처럼 문자 단위로 센다
const length = (text) => [...text].length;

export function validateRequest({ appliance, brand, modelText }) {
  if (!APPLIANCE_CODES.includes(appliance)) return "가전 종류를 골라 주세요";
  const b = String(brand ?? "").trim();
  if (!b) return "브랜드를 입력해 주세요";
  if (length(b) > 20) return "브랜드는 20자 이내로 입력해 주세요";
  const m = String(modelText ?? "").trim();
  if (!m) return "모델명을 입력해 주세요";
  if (length(m) < 2 || length(m) > 40) return "모델명은 2~40자로 입력해 주세요";
  if (!/[0-9A-Za-z]/.test(m)) return "모델명에 영문이나 숫자를 넣어 주세요";
  return null;
}

// 넣기는 세 열만(db.md: authenticated는 category·brand·model_text에만 insert 권한)
export function requestRow({ appliance, brand, modelText }) {
  return { category: appliance, brand: String(brand).trim(), model_text: String(modelText).trim() };
}

// Supabase 응답 { status, error } → 화면 문장. 하루 제한은 트리거라 P0001(HTTP 400)로 온다(2026-11-25 사용자 결정)
export function requestErrorMessage({ status, error } = {}) {
  if (status === 401) return LOGIN_REQUIRED;
  if (error?.code === "23505") return "이미 요청하셨어요";
  if (error?.code === "P0001") return "오늘은 요청을 더 받을 수 없어요. 내일 다시 요청해 주세요";
  return UNAVAILABLE;
}
