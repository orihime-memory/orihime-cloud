create table if not exists memory (
  memory_key text primary key,
  content text not null default '',
  updated_at timestamp with time zone default now()
);

create table if not exists messages (
  id bigserial primary key,
  role text not null default '',
  content text not null default '',
  created_at timestamp with time zone default now()
);

create table if not exists story_plot (
  id integer primary key,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamp with time zone default now()
);

create table if not exists chapters (
  id text primary key,
  chapter_no integer default 1,
  title text not null default '',
  content text not null default '',
  summary text not null default '',
  feedback text not null default '',
  created_at text default '',
  updated_at text default ''
);

alter table memory add column if not exists content text not null default '';
alter table memory add column if not exists updated_at timestamp with time zone default now();

alter table messages add column if not exists role text not null default '';
alter table messages add column if not exists content text not null default '';
alter table messages add column if not exists created_at timestamp with time zone default now();

alter table story_plot add column if not exists data jsonb not null default '{}'::jsonb;
alter table story_plot add column if not exists updated_at timestamp with time zone default now();

alter table chapters add column if not exists chapter_no integer default 1;
alter table chapters add column if not exists title text not null default '';
alter table chapters add column if not exists content text not null default '';
alter table chapters add column if not exists summary text not null default '';
alter table chapters add column if not exists feedback text not null default '';
alter table chapters add column if not exists created_at text default '';
alter table chapters add column if not exists updated_at text default '';

create index if not exists idx_messages_created_at on messages (created_at desc);
create index if not exists idx_chapters_chapter_no on chapters (chapter_no asc);

insert into story_plot (id, data, updated_at)
values (1, '{}'::jsonb, now())
on conflict (id) do nothing;
