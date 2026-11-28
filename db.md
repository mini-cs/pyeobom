# 펴봄 DB 구조

펴봄은 DB를 두 곳에 쓴다.

| DB | 쓰는 곳 | 구조 파일 |
|---|---|---|
| Neon Postgres + pgvector | 질문·답변(RAG): 설명서·가이드 문서, 모델 연결, 검색 조각 | `ingest/schema.sql` (1차부터) |
| Supabase (Auth + Postgres + RLS) | 2차 "내 모델 요청": 로그인, 요청 표 | `supabase/schema.sql` (이 문서) |

아래는 Supabase 쪽이다. 화면(브라우저)이 공개 키(`sb_publishable_…`)와 로그인 토큰으로 Supabase를 직접 부르므로, 누가 무엇을 읽고 넣을 수 있는지는 전부 DB의 권한·RLS·제약·트리거가 정한다.

## 표 `public.model_requests` (모델 요청)

요청자 이메일은 이 표에 두지 않는다. 이메일은 Supabase Auth(`auth.users`)에만 있다.

| 열 | 형 | 기본값·규칙 |
|---|---|---|
| `id` | `bigint` | identity(자동 번호), 기본 키 |
| `user_id` | `uuid` | 기본 `auth.uid()`(넣는 사람), `auth.users(id)` 참조, 계정을 지우면 요청도 지워짐(`on delete cascade`) |
| `category` | `text` | `washer`·`dryer`·`aircon` 중 하나 |
| `brand` | `text` | 1~20자, 공백만은 안 됨 |
| `model_text` | `text` | 2~40자, 영문·숫자 한 글자 이상 |
| `model_key` | `text` | 생성 열: `upper(regexp_replace(model_text, '[^0-9A-Za-z가-힣]', '', 'g'))` — 영문은 대문자로, 영문·숫자·한글 밖의 글자는 뺀다 |
| `status` | `text` | `대기`·`확인 중`·`추가됨`·`추가 어려움` 중 하나, 기본 `대기` |
| `reason` | `text` | 추가 어려움일 때 이유 |
| `model_id` | `text` | 추가됨일 때 `data/models.json`의 모델 id |
| `created_at` | `timestamptz` | 기본 `now()` |
| `updated_at` | `timestamptz` | 기본 `now()`, 행이 바뀌면 트리거가 갱신 |

### 제약

- `status = '추가됨'`이면 `model_id` 필수, `status = '추가 어려움'`이면 `reason` 필수
- `unique (user_id, model_key)`: 같은 사람이 정규화하면 같은 모델명(예: `AB-12`와 `ab 12`)을 두 번 요청할 수 없다. 이 색인은 `user_id`로 시작해 본인 요청 찾기(RLS·24시간 개수)에도 쓰인다
- 정규화 사례는 `tests/fixtures/model_key_cases.json`이 기준이다. 화면(Task 6)도 같은 파일로 맞춘다

### 권한 (Data API)

새 표를 자동으로 공개하지 않는 설정이라 권한을 직접 준다.

| 역할 | 읽기 | 넣기 | 수정·삭제 |
|---|---|---|---|
| `anon`(로그인 전) | 없음 | 없음 | 없음 |
| `authenticated`(로그인 후) | 있음(RLS로 본인 행만) | **`category`·`brand`·`model_text` 세 열만** | 없음 |

- 넣기는 세 열만 받는다. 화면은 이 세 열만 보내야 한다(Task 6). `user_id`·`status`·`reason`·`model_id`·`created_at`을 보내면 열 권한 오류로 거부된다. 그래서 사용자가 상태를 `추가됨`으로 넣거나 `created_at`을 과거로 넣어 하루 제한을 피할 수 없다
- `service_role`에는 이 파일에서 따로 권한을 주거나 빼지 않았다(지금 쓰는 곳 없음, Task 7·8에서 필요하면 그때 정함)
- 운영 DB 조회(2026-11-25, 채팅 Claude가 읽기만): `service_role`은 이 표에 `REFERENCES`·`TRIGGER`·`TRUNCATE`만 있고 `SELECT`·`UPDATE`가 없다(Supabase 기본값으로 보임). Task 7·8에서 서버가 이 표를 읽거나 고치게 되면 그때 권한을 준다
- identity 열의 시퀀스 권한은 주지 않았고, 넣기 테스트가 통과해 필요 없음을 확인했다

### RLS 정책

RLS를 켰다. 정책은 둘뿐이다.

| 정책 | 대상 | 내용 |
|---|---|---|
| 본인 요청만 읽기 | `select`, `authenticated` | `(select auth.uid()) = user_id` |
| 본인 요청 넣기(대기만) | `insert`, `authenticated` | 본인 행이고 `status = '대기'`, `reason`·`model_id`가 비어 있음 |

- 수정·삭제 정책은 없다. 사용자는 요청을 고치거나 지울 수 없다. 운영자는 Supabase 표 화면에서 상태를 바꾼다
- 24시간 개수 제한은 정책에 넣지 않았다. 정책 안에서 같은 표를 읽으면 Postgres가 `42P17 infinite recursion detected in policy`로 거부한다(아래 트리거로 함)

### 트리거

| 트리거 | 언제 | 하는 일 |
|---|---|---|
| `model_requests_check_daily_limit` | 넣기 직전(행마다) | 같은 사용자의 최근 24시간 요청이 5개 이상이면 `P0001` "최근 24시간 요청은 5개까지예요"로 거부 |
| `model_requests_touch_updated_at` | 수정 직전(행마다) | `updated_at`을 지금 시각으로 |

- 하루 제한 트리거는 넣는 사람의 권한으로 돌아(`security definer` 아님) 본인 요청만 센다
- 사용자별 잠금(`pg_advisory_xact_lock`)으로 같은 사용자의 넣기를 줄 세운다. 같은 사람이 동시에 여러 번 넣어도 5개를 넘지 않는다

### 거부될 때 (화면이 다룰 것)

| 경우 | 거부하는 곳 |
|---|---|
| 같은 모델명 다시 요청 | unique 제약(`23505`) |
| 24시간 6번째 요청 | 하루 제한 트리거(`P0001`) |
| 세 열 밖의 값을 보냄 | 열 권한(`42501`) |
| 로그인 안 함 | 권한 없음(`anon`) |

괄호 안은 Postgres 오류 코드다. Data API(PostgREST)가 돌려주는 HTTP 상태와 화면 문구는 아래와 같다(PostgREST v14 오류 문서로 확인, 2026-11-25 Task 6. 앞서 "Task 6에서 확인한다"고 적었던 것을 채움).

| 오류 코드 | HTTP 상태 | 화면 |
|---|---|---|
| `23505` 같은 모델명 다시 요청 | 409 | "이미 요청하셨어요" |
| `P0001` 24시간 6번째(하루 제한 트리거) | 400 | "오늘은 요청을 더 받을 수 없어요. 내일 다시 요청해 주세요" |
| `42501` 권한 없음(세 열 밖의 값·다른 사람 행 등) | 로그인 상태 403, 로그인 전 401 | 403은 "잠시 쓸 수 없어요", 401은 로그인 시트 |
| `PGRST301`·`PGRST303` 토큰 문제(만료 등) | 401 | 로그인 시트 |

### 운영 방법: 같은 모델 다시 요청

`unique (user_id, model_key)` 때문에 "추가 어려움"으로 닫힌 요청과 같은 모델명은 같은 사람이 다시 요청할 수 없다(화면은 "이미 요청하셨어요"). 다시 받으려면 운영자가 Supabase 표 화면에서 그 행을 지운다. 그러면 같은 사람이 다시 요청할 수 있다.

### 운영 방법: 삭제 요청과 데모데이 뒤 정리 (2026-11-25, 개인정보 처리방침 5절)

- 삭제 요청(pyeobom@gmail.com으로 로그인한 이메일 주소를 받음)을 받으면 두 가지를 지운다.
  1. 계정: 사용자가 SQL 편집기에서 그 이메일의 `auth.users` 행을 지운다. 요청(`model_requests`)은 `on delete cascade`로 함께 지워진다.
  2. 운영자 메일함(pyeobom@gmail.com)에서 그 사람과 관련된 알림 메일과 답장 메일을 지운다.
- 데모데이 뒤 2차 테스트 기간의 계정·요청 정리도 같은 방법으로 한다(계정 삭제 + 운영자 메일함의 관련 메일 삭제).
- 이미 발급된 로그인 토큰은 계정을 지워도 만료 전까지는 유효하다(Supabase 문서 managing-user-data).

### 확인한 테스트

`tests/requests/test_rls_live.py`(integration, 실제 Supabase, OpenAI 비용 0). 가짜 시험 사용자(`fake-rls-…@example.com`)를 관리 API로 만들고, 끝나면 테스트가 만든 사용자만 지운다.

- `test_user_sees_only_own_requests`, `test_user_cannot_update_or_delete`, `test_insert_with_status_added_is_rejected`, `test_duplicate_model_key_is_rejected`(409·`23505`), `test_sixth_request_in_24h_is_rejected`(400·`P0001`), `test_model_key_matches_cases_live`, `test_insert_for_other_user_is_rejected`(403·`42501`), `test_anon_cannot_read_requests`(401·`42501`)

## Supabase 보안 점검 경고와 판단 (2026-11-25)

| 경고 | 판단 |
|---|---|
| `public.rls_auto_enable()`: 이벤트 트리거 `ensure_rls`가 쓰는 `SECURITY DEFINER` 함수. 이 프로젝트가 만들지 않았고, 만든 쪽은 확인하지 못함 | 지금은 그대로 둔다 |
| 유출 비밀번호 막기(leaked password protection) 꺼짐 | 비밀번호 로그인을 쓰지 않아(이메일 코드·구글) 해당 없음 |

## 웹훅 (Task 7)

요청이 들어오거나(INSERT) 상태가 바뀌면(UPDATE) 데이터베이스 웹훅이 알림 주소(`/api/notify`)를 부르고, 운영자·요청자에게 메일이 간다(`app/notify/`).

| 항목 | 값 |
|---|---|
| 표·이벤트 | `public.model_requests`의 INSERT, UPDATE (웹훅 1개(이벤트 INSERT·UPDATE), 이름 `notify_model_requests`) |
| 주소 | POST https://pyeobom.help/api/notify (U7에서 등록, 2026-11-25) |
| 시간 제한 | 5000ms |
| 머리글 | `x-pyeobom-webhook-secret: <NOTIFY_WEBHOOK_SECRET>` (값은 Vercel·Supabase에만, 여기에 적지 않음) |
| 본문 | Supabase 데이터베이스 웹훅 형식 `type`·`table`·`schema`·`record`·`old_record` |

- 보내는 규칙: INSERT → 운영자 메일. UPDATE → 상태가 바뀌었고 새 상태가 "추가됨"·"추가 어려움"일 때만 요청자 메일(답장 주소는 운영자). "추가됨"인데 그 `model_id`가 이 배포의 `data/models.json`에 없으면 보내지 않는다.
- 응답: 200 `{"sent": "operator" | "requester" | "none", "reason": …}`. `reason`은 `inserted`·`status_changed`·`status_unchanged`·`status_not_final`·`not_deployed`·`other_table`·`ignored_type`.
- 401: 머리글 비밀 값이 없거나 틀림, 또는 서버에 비밀 값이 설정되지 않음(본문을 읽지 않음). 400: 본문이 JSON 객체가 아니거나 필요한 필드가 빠짐. 502: 메일을 보내지 못함(Resend·관리 API 실패, 10초 시간 초과, 설정 없음).
- 다시 보내기: 표 화면에서 status를 "확인 중"으로 되돌렸다가 다시 "추가됨"·"추가 어려움"으로 바꾼다(같은 값으로 다시 저장하면 보내지 않음). `not_deployed`였으면 배포가 끝난 뒤 같은 방법으로.
- 로그에는 요청 id·status·결과만 남는다(메일·모델명·user_id·키 없음).
- 응답 기록은 SQL 편집기에서 `net._http_response`로 확인한다(상태 코드·시간 초과 여부).

### 메일 한도 (공식 문서 확인: 채팅 Claude, 2026-11-25)

- Resend 무료: 하루 100통(UTC 기준 하루, 보낸 메일과 받은 메일을 합산, SMTP도 같은 한도). 넘으면 429이고 다시 보내 주지 않는다.
- Supabase 사용자 지정 SMTP: 기본 시간당 30통.
- 로그인 코드 메일(Supabase → Resend SMTP), 알림 메일(Resend API), Task 11의 받기 확인이 같은 100통을 나눠 쓴다 → Task 11 계획 때 다시 본다.

## Supabase 깨우기 (Task 11 ③)

설계 `docs/superpowers/specs/2026-11-28-supabase-wake-design.md`. Supabase 무료 플랜은 지난 일주일 사용자 데이터베이스 활동이 충분하지 않으면 프로젝트를 멈춘다(Supabase 문서 "Project Pausing"). 질문·답변은 Neon이라 Supabase는 로그인·요청 때만 불리므로, 방문이 줄어도 멈추지 않게 Vercel Cron이 하루 3번 요청 표를 1줄 읽는다.

| 항목 | 값 |
|---|---|
| 주소 | GET https://pyeobom.help/api/wake (`app/wake/`) |
| Cron(UTC, `vercel.json`) | `23 1 * * *`, `23 9 * * *`, `23 17 * * *` (Hobby는 작업마다 하루 1번, 정한 시각의 한 시간 안 어느 때) |
| 인증 | `Authorization: Bearer <CRON_SECRET>` (Vercel Cron이 보냄. 값은 Vercel Production에만, 여기에 적지 않음. 서버는 앞뒤 빈칸을 떼고 비교) |
| 읽기 | `GET /rest/v1/model_requests?select=id&limit=1`, 머리글 `apikey`에 비밀 키만, 시간 제한 10초. 결과는 버림(표 내용은 바꾸지 않음) |

- 응답: 200 `{"ok": true}`. 401: 머리글이 없거나 틀림, 또는 서버에 `CRON_SECRET`이 없음(Supabase를 부르지 않음). 502: `reason`이 `not_configured`·`rest_<상태숫자>`·`<httpx 예외 이름>`.
- 로그: `wake: result=ok` / `wake: result=unauthorized` / `wake 실패: reason=…`(키·주소·응답 본문 없음).
- Neon·Vercel은 깨우지 않는다(2차 계획 덧붙임 G).
- 한계: 하루 3번 1줄 읽기가 Supabase의 "충분한 활동"에 드는지는 기준이 공개되지 않아 확인할 수 없다(멈추기 약 일주일 전 경고 메일이 오면 횟수를 늘린다). Vercel Cron은 최선 노력이라 가끔 빠질 수 있고, 실패해도 다시 하지 않으며, legacy라 나중에 Schedules로 옮겨야 할 수 있다. `CRON_SECRET`은 배포가 만들어질 때의 값을 쓴다(넣은 뒤 다시 배포해야 반영).
