# 2차 Task 11 ③ Supabase 깨우기 — Vercel Cron이 하루 3번 요청 표를 1줄 읽음 (짧은 설계)

- 날짜: 2026-11-28
- 상태: 확정(사용자 승인 2026-11-28)
- 관련: 2차 설계 `docs/superpowers/specs/2026-11-17-phase2-model-request-design.md` 10-7(Supabase가 멈춰도 질문은 그대로)·14-5(깨우기 예약 방법은 계획 때, 2차가 끝나기 전에), 2차 계획 `docs/superpowers/plans/2026-11-21-phase2-model-request-plan.md` Task 11 Step 3·덧붙임 G(Neon·Vercel 깨우기는 안 함), 알림 주소 `app/notify/routes.py`(비밀 값 확인 방식)
- 크기: 앱 코드 작은 변경(주소 하나 + 설정 한 칸 + vercel.json). Task 11의 셋째, 코드 동결 전

## 왜

- Supabase 무료 플랜은 지난 일주일 "사용자 데이터베이스 활동"이 충분하지 않으면 프로젝트를 멈춘다(Supabase 문서 "Project Pausing", 2026-09-22 갱신). 펴봄은 질문·답변이 Neon이라 Supabase는 로그인·요청 때만 불린다. 데모데이 뒤 방문이 줄면 멈출 수 있고, 멈추면 로그인·요청이 "잠시 쓸 수 없어요"가 된다(질문은 그대로, 설계 10-7)
- 2차가 끝난 뒤 포트폴리오로 둘 때도 사람 손 없이 로그인·요청이 살아 있게 한다

## 정한 것 (사용자 결정 2026-11-28)

1. Vercel Cron → 새 주소 `GET /api/wake`. 서버가 이미 가진 Supabase 비밀 키로 요청 표를 1줄 읽고 결과는 버린다(GitHub Actions 예약·자동으로 안 깨우기는 고르지 않음)

## 고른 방법과 고르지 않은 것

- 고름: **Vercel Cron**. 키가 Vercel 밖으로 나가지 않고, 저장소가 조용해져도 꺼지지 않는다
- 고르지 않음: GitHub Actions 예약(같은 주소가 필요하고 비밀 값을 GitHub에도 둬야 함, 공개 저장소에 60일 활동이 없으면 예약이 저절로 꺼짐, 부하 때 늦어지거나 빠짐 — GitHub 문서 "Events that trigger workflows"), 자동으로 안 깨우기(멈추기 약 일주일 전 경고 메일을 보고 대시보드를 열어 깨움 — 메일을 놓치면 멈추고, 계획 Task 11 Step 3과 다름)

## 확인한 사실 (공식 문서, 2026-11-28)

- Supabase: 정확한 기준은 공개하지 않고 "하루에 몇 번의 사용자 DB 요청이면 보통 충분"이라고만 씀. 멈추기 약 일주일 전 경고 메일, 멈춘 뒤에도 복구 가능(본문은 1년, 같은 페이지 제목은 90일로 서로 다름). 새 비밀 키(`sb_secret_`)는 JWT가 아니라 `apikey` 머리글로 보냄("Migrating to publishable and secret API keys")
- Vercel Cron(문서 "Usage & Pricing for Cron Jobs" 2026-07-15, "Managing Cron Jobs" 2026-08-11): Hobby는 작업마다 하루 1번, 정한 시각의 한 시간 안 어느 때(±59분), 프로젝트당 100개. 하루에 두 번 이상 도는 식은 배포가 실패함. 운영 배포에서만 돌고 실패해도 다시 하지 않음(전달은 최선 노력, 가끔 빠지거나 두 번 옴). `CRON_SECRET` 환경 변수가 있으면 `Authorization: Bearer <값>`으로 보냄. 배포가 만들어질 때의 값을 씀(넣은 뒤 다시 배포해야 반영). 이동(3xx)은 따라가지 않음. Cron은 "legacy"이고 나중에 Schedules(베타)로 옮긴다고 함

## 동작

1. `vercel.json`에 `crons` 3개: 모두 `"path": "/api/wake"`, 하루 1번씩 서로 다른 시각(UTC 01·09·17시대, 분은 0이 아닌 값). 하루 3번 → "하루에 몇 번"에 맞춤
2. `GET /api/wake`
   - `CRON_SECRET`이 비어 있으면 모두 401(알림 주소와 같은 방식, `hmac.compare_digest`). `Authorization`이 `Bearer <CRON_SECRET>`와 다르면 401. 401일 때는 Supabase를 부르지 않음
   - 맞으면 Supabase `GET /rest/v1/model_requests?select=id&limit=1`(머리글 `apikey`에 비밀 키만, `Authorization`은 보내지 않음, 시간 제한 10초)을 스레드에서 부르고 결과는 버림
   - 200이면 `{"ok": true}`. Supabase가 200이 아니거나 연결이 실패하면 502 `{"error_code": "WAKE_FAILED", "reason": "<rest_상태숫자 또는 예외 이름>"}`. Supabase 설정이 비면 502 `reason: "not_configured"`
   - 로그는 정해진 형식 한 줄(`wake: result=ok` / `wake 실패: reason=…`). 키·주소·응답 본문은 로그·응답에 넣지 않음
3. 설정 `cron_secret`(환경 변수 `CRON_SECRET`) 한 칸. `.env.example`에 이름만(설명: 운영 Vercel Production에만, 로컬은 비워 둠)

## 하지 않을 것

- Neon·Vercel 깨우기(덧붙임 G), 표 내용 바꾸기(읽기만), 새 표·함수(구조 SQL 없음)
  - Neon은 무료 플랜에서 5분 쉬면 계산 서버가 잠들고 다음 질문에 저절로 깨며("수백 밀리초"), 24시간 접속이 없으면 브랜치가 보관됐다가 다음 접속에 저절로 풀린다. 오래 안 써도 지우는 규정은 Free 플랜 안내(2026-11-03·11-09)와 이용 약관(2026-10-14)에서 찾지 못함(채팅 Claude 확인 2026-11-28). 5분보다 자주 깨우면 무료 계산 시간(프로젝트당 월 100 CU-시간)을 넘겨 오히려 멈출 수 있음 → 사용자 "정한 대로"(2026-11-28)
- Schedules(베타)로 만들기(Cron이 문서·제한이 정해져 있음)

## 실패로 볼 것

- 키·`CRON_SECRET` 값이 응답·로그·저장소·보고에 남음
- 비밀 값 없이 부른 요청이 Supabase까지 감
- 질문·답변·로그인·요청 흐름이 바뀜

## 사용자 작업

- 병합 전: Vercel 프로젝트 환경 변수에 `CRON_SECRET`(영문·숫자 32자 이상, Production) 추가. 값은 채팅·저장소에 붙이지 않음(단계별 가이드는 채팅 Claude가 줌)

## 확인 (병합 뒤)

- 운영 `GET /api/wake`를 비밀 값 없이 부르면 401(Claude Code)
- Vercel 대시보드 Cron Jobs 탭의 첫 실행 기록이 200(사용자 또는 Claude Code, 정한 시각의 한 시간 안)
- Supabase 로그에 그 시각의 `model_requests` 읽기가 보이는지(채팅 Claude, Supabase 연결 도구로 읽기만)

## 한계

- 하루 3번 1줄 읽기가 Supabase의 "충분한 활동"에 드는지는 기준이 공개되지 않아 확인할 수 없다. 요청이 DB에 닿는 것까지만 확인한다. 그래도 멈추면 경고 메일이 오므로 그때 횟수를 늘린다
- Vercel Cron은 가끔 빠질 수 있고(최선 노력), legacy라 나중에 Schedules로 옮겨야 할 수 있다
- Vercel 프로젝트를 지우거나 Cron을 끄면 깨우기도 멈춘다

## 만드는 사람에게 맡김

- 모듈 위치(`app/wake/` 또는 그 밖)와 함수 이름, 시각의 정확한 분, 테스트 이름
