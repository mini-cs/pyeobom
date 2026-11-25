import test from "node:test";
import assert from "node:assert/strict";
import { signInMethod } from "../../../public/js/auth.js";

// 모양만 JWT인 가짜 토큰(서명 없음). amr은 가장 최근 방식이 맨 앞(Supabase 문서 auth-mfa)
const b64 = (obj) => Buffer.from(JSON.stringify(obj)).toString("base64url");
const token = (payload) => `${b64({ alg: "HS256", typ: "JWT" })}.${b64(payload)}.fake-signature`;
const session = (amr) => ({ access_token: token({ sub: "fake", amr }) });

test("signInMethod: 구글(oauth)이면 Google 계정", () =>
  assert.equal(signInMethod(session([{ method: "oauth", timestamp: 2 }])), "Google 계정"));
test("signInMethod: 메일 코드(otp·magiclink·email/signup)면 메일 코드 계정", () => {
  for (const method of ["otp", "magiclink", "email/signup"]) {
    assert.equal(signInMethod(session([{ method, timestamp: 2 }])), "메일 코드 계정", method);
  }
});
test("signInMethod: 같은 계정에 두 방식이 묶여도 지금(맨 앞) 방식", () => {
  assert.equal(signInMethod(session([{ method: "oauth", timestamp: 3 }, { method: "otp", timestamp: 1 }])), "Google 계정");
  assert.equal(signInMethod(session([{ method: "otp", timestamp: 3 }, { method: "oauth", timestamp: 1 }])), "메일 코드 계정");
});
test("signInMethod: 모르는 방식은 건너뛰고 다음 것", () =>
  assert.equal(signInMethod(session([{ method: "token_refresh", timestamp: 3 }, { method: "otp", timestamp: 1 }])), "메일 코드 계정"));
test("signInMethod: 알 수 없으면 null(표시 안 함)", () => {
  assert.equal(signInMethod(null), null);
  assert.equal(signInMethod({ access_token: "not-a-jwt" }), null);
  assert.equal(signInMethod(session(undefined)), null);
  assert.equal(signInMethod(session([{ method: "password", timestamp: 1 }])), null);
});
