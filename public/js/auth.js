// 로그인(Supabase Auth, 계획 Task 6). 공개 설정(/api/public-config)을 받은 뒤에야 supabase-js를 불러 만든다:
// 처음 화면에서는 아무것도 부르지 않는다. supabase-js는 public/vendor/supabase.js(UMD, window.supabase)
export const isOtpCode = (text) => /^\d{6,10}$/.test(String(text ?? ""));  // 덧붙임 A-2: 숫자 6~10자리, 길이 고정 안 함

// 지금 로그인 방식(L1): 세션 토큰의 amr(가장 최근 방식이 맨 앞, Supabase 문서 auth-mfa). app_metadata.provider·providers는
// 처음 가입 방식·묶인 방식 목록이라 같은 메일로 두 방식이 묶이면 지금 방식을 모른다. 표시용이라 서명은 확인하지 않는다.
// oauth는 구글만 켜 두었으므로 "Google 계정"
const METHODS = { oauth: "Google 계정", otp: "메일 코드 계정", magiclink: "메일 코드 계정", "email/signup": "메일 코드 계정" };
export function signInMethod(session) {
  try {
    const part = String(session?.access_token ?? "").split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const claims = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(part), (c) => c.charCodeAt(0))));
    for (const entry of claims.amr ?? []) {
      if (METHODS[entry?.method]) return METHODS[entry.method];
    }
  } catch { /* 토큰 모양이 다르면 표시하지 않는다 */ }
  return null;
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (globalThis.supabase) return resolve();
    const s = document.createElement("script");
    s.src = src;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("supabase-js"));
    document.head.append(s);
  });
}

async function create() {
  const res = await fetch("/api/public-config");
  if (!res.ok) throw new Error(String(res.status));
  const { supabase_url: url, supabase_anon_key: key } = await res.json();
  await loadScript("/vendor/supabase.js");
  // PKCE: 구글에서 돌아올 때 토큰이 주소 # 뒤가 아니라 ?code=로 와서 우리 # 경로와 부딪치지 않는다(받은 code는 자동으로 세션으로 바꿈)
  const client = globalThis.supabase.createClient(url, key, {
    auth: { flowType: "pkce", detectSessionInUrl: true, persistSession: true, autoRefreshToken: true },
  });
  // 콜백 안에서 바로 다른 Supabase 호출을 하지 않게 다음 차례로 미룬다
  client.auth.onAuthStateChange((event, session) => {
    setTimeout(() => listeners.forEach((f) => f(event, session)), 0);
  });
  return {
    client,
    async session() {
      const { data } = await client.auth.getSession();
      return data.session;
    },
    async sendCode(email) {
      const { error } = await client.auth.signInWithOtp({ email });
      return error;
    },
    async verifyCode(email, code) {
      const { error } = await client.auth.verifyOtp({ email, token: code, type: "email" });
      return error;
    },
    google(redirectTo) {
      return client.auth.signInWithOAuth({ provider: "google", options: { redirectTo } });
    },
    signOut() {  // 이 기기만(다른 기기 세션은 그대로). 실패하면 { error }
      return client.auth.signOut({ scope: "local" });
    },
  };
}

// 로그인 상태가 바뀌면(로그아웃·토큰 만료·새 로그인) 알린다. Supabase를 만들기 전에도 등록할 수 있다
const listeners = [];
export function onAuthChange(callback) {
  listeners.push(callback);
}

let pending = null;
// 실패(공개 설정 503·연결 끊김)면 null이고, 다음에 다시 시도한다
export function initAuth() {
  pending ??= create().catch(() => {
    pending = null;
    return null;
  });
  return pending;
}
