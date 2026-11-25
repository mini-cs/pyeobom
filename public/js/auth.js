// 로그인(Supabase Auth, 계획 Task 6). 공개 설정(/api/public-config)을 받은 뒤에야 supabase-js를 불러 만든다:
// 처음 화면에서는 아무것도 부르지 않는다. supabase-js는 public/vendor/supabase.js(UMD, window.supabase)
export const isOtpCode = (text) => /^\d{6,10}$/.test(String(text ?? ""));  // 덧붙임 A-2: 숫자 6~10자리, 길이 고정 안 함

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
    signOut() {
      return client.auth.signOut();
    },
  };
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
