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

괄호 안은 Postgres 오류 코드다. Data API가 이것을 어떤 HTTP 상태로 돌려주는지는 Task 6에서 확인한다(지금 테스트는 "400 이상"만 본다).

### 확인한 테스트

`tests/requests/test_rls_live.py`(integration, 실제 Supabase, OpenAI 비용 0). 가짜 시험 사용자(`fake-rls-…@example.com`)를 관리 API로 만들고, 끝나면 테스트가 만든 사용자만 지운다.

- `test_user_sees_only_own_requests`, `test_user_cannot_update_or_delete`, `test_insert_with_status_added_is_rejected`, `test_duplicate_model_key_is_rejected`, `test_sixth_request_in_24h_is_rejected`, `test_model_key_matches_cases_live`

## 웹훅 (Task 7에서 채움)

요청이 들어오거나(INSERT) 상태가 바뀌면(UPDATE) 데이터베이스 웹훅이 알림 주소(`/api/notify`)를 부르고, 운영자·요청자에게 메일이 간다. 웹훅 설정과 보내는 값은 Task 7에서 이 절에 적는다.
