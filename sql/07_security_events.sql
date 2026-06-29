-- VinoSage 2.0: audit of blocked/flagged prompt-injection and memory-injection
-- attempts. Service-role only (like all log tables) — never visible to users.
create table if not exists security_events (
  id           uuid primary key default gen_random_uuid(),
  created_at   timestamptz not null default now(),
  session_id   text not null,
  user_id      uuid references auth.users(id) on delete set null,  -- null for anon
  locale       text,
  event_type   text not null default 'prompt_injection'
                 check (event_type in ('prompt_injection','memory_injection','jailbreak','off_topic_abuse')),
  severity     text not null default 'low' check (severity in ('low','medium','high')),
  user_query   text not null,            -- the offending input (truncated to 2000 chars by the writer)
  matched_rule text,                     -- which detector fired (for tuning false positives)
  action_taken text not null default 'blocked' check (action_taken in ('blocked','flagged','allowed')),
  model        text
);
create index if not exists idx_sec_events_user on security_events(user_id);
create index if not exists idx_sec_events_time on security_events(created_at desc);

alter table security_events enable row level security;
create policy sec_service on security_events
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
