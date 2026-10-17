-- Run once in Supabase: SQL Editor > New query > paste > Run
create table if not exists profiles (
  username text primary key,
  data jsonb not null,
  updated_at timestamptz default now()
);
create table if not exists history (
  id bigint generated always as identity primary key,
  username text not null,
  created_at timestamptz default now(),
  title text, company text, source text, status text default 'Applied',
  score int, text text
);
create index if not exists history_user_idx on history (username, created_at desc);
create table if not exists ai_usage (
  username text not null, day date not null, count int not null default 0,
  primary key (username, day)
);
-- The app uses the service-role key from the server. Keep row level security ON
-- so the public anon key can never read these tables.
alter table profiles enable row level security;
alter table history enable row level security;
alter table ai_usage enable row level security;
