-- 펴봄 2차: 모델 요청 표 (계획 Task 4, 설계 7절)
-- 실행: 사용자가 Supabase SQL 편집기에서 한 번 실행한다(U6). 다시 실행하면 create에서 멈춘다(덮어쓰지 않음).
-- 요청자 이메일은 이 표에 두지 않는다(Supabase Auth에만, Global 2).

begin;

create table public.model_requests (
  id bigint generated always as identity primary key,
  -- 계정을 지우면 요청도 함께 지워진다(데모데이 뒤 정리)
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  category text not null check (category in ('washer', 'dryer', 'aircon')),
  brand text not null check (char_length(brand) between 1 and 20 and btrim(brand) <> ''),
  model_text text not null check (char_length(model_text) between 2 and 40 and model_text ~ '[0-9A-Za-z]'),
  -- 영문은 대문자로, 영문·숫자·한글 밖의 글자는 모두 뺀다(화면은 tests/fixtures/model_key_cases.json으로 맞춤)
  model_key text generated always as (upper(regexp_replace(model_text, '[^0-9A-Za-z가-힣]', '', 'g'))) stored,
  status text not null default '대기' check (status in ('대기', '확인 중', '추가됨', '추가 어려움')),
  reason text,
  model_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint model_requests_added_needs_model_id check (status <> '추가됨' or model_id is not null),
  constraint model_requests_rejected_needs_reason check (status <> '추가 어려움' or reason is not null),
  -- user_id가 앞이라 본인 요청 찾기(RLS·24시간 개수)에도 이 색인을 쓴다
  constraint model_requests_user_model_key_unique unique (user_id, model_key)
);

create function public.model_requests_touch_updated_at() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger model_requests_touch_updated_at
  before update on public.model_requests
  for each row execute function public.model_requests_touch_updated_at();

alter table public.model_requests enable row level security;

create policy "본인 요청만 읽기" on public.model_requests
  for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "본인 요청 넣기(대기만)" on public.model_requests
  for insert to authenticated
  with check (
    (select auth.uid()) = user_id
    and status = '대기'
    and reason is null
    and model_id is null
  );
-- UPDATE·DELETE 정책은 두지 않는다(사용자 불가, 운영자는 표 화면에서)

-- 정책 안에서 같은 표를 읽으면 무한 반복 오류(42P17)라 개수 제한은 넣기 직전 트리거로 한다.
-- 넣는 사람 권한으로 돌아 본인 요청만 센다. 같은 사용자의 넣기는 잠금으로 줄 세워 동시에 넣어도 5개를 넘지 않는다
create function public.model_requests_check_daily_limit() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(new.user_id::text, 0));
  if (
    select count(*) from public.model_requests r
    where r.user_id = new.user_id and r.created_at > now() - interval '24 hours'
  ) >= 5 then
    raise exception '최근 24시간 요청은 5개까지예요' using errcode = 'P0001';
  end if;
  return new;
end;
$$;

create trigger model_requests_check_daily_limit
  before insert on public.model_requests
  for each row execute function public.model_requests_check_daily_limit();

-- 새 표 자동 공개가 꺼져 있어 권한을 직접 준다(덧붙임 A-1). anon에는 주지 않는다
revoke all on table public.model_requests from anon, authenticated;
grant select on table public.model_requests to authenticated;
-- 넣기는 화면이 보내는 세 열만: user_id·status·created_at 등을 사용자가 정할 수 없게 한다(24시간 개수를 created_at으로 피하는 것도 막음)
grant insert (category, brand, model_text) on table public.model_requests to authenticated;
-- 깨우기(/api/wake, 2차 Task 11 ③)가 서버 키(service_role)로 1줄 읽는다. 새 표를 자동으로 열지 않는 프로젝트라 직접 준다(읽기만)
grant select on table public.model_requests to service_role;

commit;
